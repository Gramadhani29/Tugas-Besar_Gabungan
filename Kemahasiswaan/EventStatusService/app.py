from flask import Flask, jsonify, request
import requests
import os
import graphene
from graphene import ObjectType, String, Int, Field, List

app = Flask(__name__)

ADD_EVENT_SERVICE = os.getenv('ADD_EVENT_SERVICE_URL', 'http://localhost:5008')
ROOM_BOOKING_STATUS_SERVICE = os.getenv('ROOM_BOOKING_STATUS_SERVICE_URL', 'http://localhost:5012')

# GraphQL Types
class EventStatusType(ObjectType):
    event_id = Int()
    status_approval = String()
    status_booking = String()
    keterangan_reject = String()

# GraphQL Mutations
class SetEventStatus(graphene.Mutation):
    class Arguments:
        event_id = Int(required=True)
        status = String(required=True)
        rejection_reason = String()

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, event_id, status, rejection_reason=None):
        try:
            if not hasattr(app, 'event_statuses'):
                app.event_statuses = {}
                
            app.event_statuses[event_id] = {
                'status': status,
                'rejection_reason': rejection_reason
            }
            
            return SetEventStatus(success=True, message='Event status updated successfully')
        except Exception as e:
            return SetEventStatus(success=False, message=str(e))

# GraphQL Queries
class Query(ObjectType):
    all_event_statuses = List(EventStatusType)
    event_status = Field(EventStatusType, event_id=Int(required=True))

    def resolve_all_event_statuses(self, info):
        if not hasattr(app, 'event_statuses'):
            app.event_statuses = {}
        return [{'event_id': k, **v} for k, v in app.event_statuses.items()]

    def resolve_event_status(self, info, event_id):
        try:
            # Get approval status from add_event_service
            event_resp = requests.get(f"{ADD_EVENT_SERVICE}/api/events/{event_id}")
            if event_resp.status_code != 200:
                return None
            event = event_resp.json()
            status_approval = event.get('status_approval', 'Unknown')

            # Get booking status from RoomBookingStatusService
            try:
                booking_resp = requests.get(f"{ROOM_BOOKING_STATUS_SERVICE}/api/room-booking-status/{event_id}")
                if booking_resp.status_code == 200:
                    booking = booking_resp.json()
                    status_booking = booking.get('status_booking', 'Not Booked')
                    keterangan_reject = booking.get('keterangan_reject', '')
                else:
                    status_booking = 'Not Booked'
                    keterangan_reject = ''
            except Exception:
                status_booking = 'Not Booked'
                keterangan_reject = ''

            return {
                'event_id': event_id,
                'status_approval': status_approval,
                'status_booking': status_booking,
                'keterangan_reject': keterangan_reject
            }
        except Exception as e:
            return None

class Mutation(ObjectType):
    set_event_status = SetEventStatus.Field()

schema = graphene.Schema(query=Query, mutation=Mutation)

@app.route("/graphql", methods=["GET", "POST"])
def graphql():
    if request.method == "GET":
        graphiql_html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>GraphiQL</title>
            <link href="https://cdn.jsdelivr.net/npm/graphiql@2.0.9/graphiql.min.css" rel="stylesheet" />
        </head>
        <body style="margin: 0;">
            <div id="graphiql" style="height: 100vh;"></div>
            <script crossorigin src="https://cdn.jsdelivr.net/npm/react@18/umd/react.production.min.js"></script>
            <script crossorigin src="https://cdn.jsdelivr.net/npm/react-dom@18/umd/react-dom.production.min.js"></script>
            <script crossorigin src="https://cdn.jsdelivr.net/npm/graphiql@2.0.9/graphiql.min.js"></script>
            <script>
                const graphQLFetcher = graphQLParams =>
                    fetch('/graphql', {
                        method: 'post',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(graphQLParams),
                    })
                    .then(response => response.json())
                    .catch(error => {
                        console.error('Fetch error:', error);
                        return { errors: [{ message: error.message }] };
                    });

                const rootElement = document.getElementById('graphiql');
                if (ReactDOM.createRoot) {
                    ReactDOM.createRoot(rootElement).render(
                        React.createElement(GraphiQL, { fetcher: graphQLFetcher })
                    );
                } else {
                    ReactDOM.render(
                        React.createElement(GraphiQL, { fetcher: graphQLFetcher }),
                        rootElement
                    );
                }
            </script>
        </body>
        </html>
        '''
        return graphiql_html, 200, {'Content-Type': 'text/html'}

    data = request.get_json()
    if not data:
        return jsonify({"error": "No input data provided"}), 400

    result = schema.execute(
        data.get("query"),
        variables=data.get("variables"),
        operation_name=data.get("operationName"),
        context_value=request,
    )

    response = {}
    if result.errors:
        response["errors"] = [str(e) for e in result.errors]
    if result.data:
        response["data"] = result.data

    status_code = 200 if not result.errors else 400
    return jsonify(response), status_code

# Existing REST endpoints
@app.route('/api/events/status', methods=['POST'])
def set_event_status():
    try:
        data = request.json
        if not data or 'event_id' not in data or 'status' not in data:
            return jsonify({'error': 'Missing required fields'}), 400
            
        # Store the status in memory (you might want to use a database in production)
        if not hasattr(app, 'event_statuses'):
            app.event_statuses = {}
            
        app.event_statuses[data['event_id']] = {
            'status': data['status'],
            'rejection_reason': data.get('rejection_reason')
        }
        
        return jsonify({'message': 'Event status updated successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/events/status', methods=['GET'])
def get_all_event_statuses():
    try:
        if not hasattr(app, 'event_statuses'):
            app.event_statuses = {}
        return jsonify([{'event_id': k, **v} for k, v in app.event_statuses.items()]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/events/<int:event_id>/status', methods=['GET'])
def get_event_status(event_id):
    # Get approval status from add_event_service
    try:
        event_resp = requests.get(f"{ADD_EVENT_SERVICE}/api/events/{event_id}")
        if event_resp.status_code != 200:
            return jsonify({'error': 'Event not found'}), 404
        event = event_resp.json()
        status_approval = event.get('status_approval', 'Unknown')
    except Exception as e:
        return jsonify({'error': f'Failed to get event: {str(e)}'}), 500

    # Get booking status from RoomBookingStatusService
    try:
        booking_resp = requests.get(f"{ROOM_BOOKING_STATUS_SERVICE}/api/room-booking-status/{event_id}")
        if booking_resp.status_code == 200:
            booking = booking_resp.json()
            status_booking = booking.get('status_booking', 'Not Booked')
            keterangan_reject = booking.get('keterangan_reject', '')
        else:
            status_booking = 'Not Booked'
            keterangan_reject = ''
    except Exception:
        status_booking = 'Not Booked'
        keterangan_reject = ''

    return jsonify({
        'event_id': event_id,
        'status_approval': status_approval,
        'status_booking': status_booking,
        'keterangan_reject': keterangan_reject
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5011, debug=True) 