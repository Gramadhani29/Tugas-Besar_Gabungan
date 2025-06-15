from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from datetime import datetime, timedelta
import logging
import os
import graphene
from graphene import ObjectType, String, Int, Field, List, Boolean

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Service URLs
ADD_EVENT_SERVICE = os.getenv("ADD_EVENT_SERVICE_URL", "http://add_event_service:5008")

# GraphQL Types
class CalendarEventType(ObjectType):
    id = Int()
    title = String()
    start = String()
    end = String()
    description = String()
    status = String()
    color = String()
    textColor = String()
    borderColor = String()
    display = String()
    allDay = Boolean()
    extendedProps = Field(lambda: ExtendedPropsType)

class ExtendedPropsType(ObjectType):
    status = String()
    description = String()
    duration = Int()
    isMultiDay = Boolean()

# GraphQL Queries
class Query(ObjectType):
    calendar_events = List(CalendarEventType)

    def resolve_calendar_events(self, info):
        try:
            # Fetch events from add_event_service
            response = requests.get(f"{ADD_EVENT_SERVICE}/api/events")
            if response.status_code != 200:
                return []

            events = response.json()
            
            # Transform events into calendar format
            calendar_events = []
            for event in events:
                # Hanya tampilkan event yang statusnya bukan 'Rejected'
                if event.get('status_approval') == 'Rejected':
                    continue
                # Convert string dates to datetime objects
                start_date = datetime.strptime(event['tanggal_mulai'], '%Y-%m-%d')
                end_date = datetime.strptime(event['tanggal_selesai'], '%Y-%m-%d')
                
                # Add one day to end_date to make it inclusive in the calendar
                end_date = end_date + timedelta(days=1)
                
                # Create calendar event with enhanced information
                calendar_event = {
                    'id': event['event_id'],
                    'title': event['nama_event'],
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat(),
                    'description': event['deskripsi'],
                    'status': event['status_approval'],
                    'color': get_status_color(event['status_approval']),
                    'textColor': '#ffffff',  # White text for better contrast
                    'borderColor': get_status_border_color(event['status_approval']),
                    'display': 'block',  # Show as block to make it more visible
                    'allDay': True,  # Show as all-day event
                    'extendedProps': {
                        'status': event['status_approval'],
                        'description': event['deskripsi'],
                        'duration': (end_date - start_date).days,
                        'isMultiDay': (end_date - start_date).days > 1
                    }
                }
                calendar_events.append(calendar_event)

            return calendar_events
        except Exception as e:
            logger.error(f"Error fetching calendar events: {str(e)}")
            return []

schema = graphene.Schema(query=Query)

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

def get_status_color(status):
    """Return color based on event status"""
    colors = {
        'Pending': '#FFA500',  # Orange
        'Approved': '#4CAF50',  # Green
        'Rejected': '#F44336',  # Red
        'Room Booked': '#2196F3'  # Blue
    }
    return colors.get(status, '#808080')  # Default gray

def get_status_border_color(status):
    """Return border color based on event status"""
    colors = {
        'Pending': '#E69500',  # Darker Orange
        'Approved': '#388E3C',  # Darker Green
        'Rejected': '#D32F2F',  # Darker Red
        'Room Booked': '#1976D2'  # Darker Blue
    }
    return colors.get(status, '#666666')  # Default darker gray

# Existing REST endpoint
@app.route('/api/calendar-events', methods=['GET'])
def get_calendar_events():
    try:
        # Fetch events from add_event_service
        response = requests.get(f"{ADD_EVENT_SERVICE}/api/events")
        if response.status_code != 200:
            return jsonify({'error': 'Failed to fetch events'}), 500

        events = response.json()
        
        # Transform events into calendar format
        calendar_events = []
        for event in events:
            # Hanya tampilkan event yang statusnya bukan 'Rejected'
            if event.get('status_approval') == 'Rejected':
                continue
            # Convert string dates to datetime objects
            start_date = datetime.strptime(event['tanggal_mulai'], '%Y-%m-%d')
            end_date = datetime.strptime(event['tanggal_selesai'], '%Y-%m-%d')
            
            # Add one day to end_date to make it inclusive in the calendar
            end_date = end_date + timedelta(days=1)
            
            # Create calendar event with enhanced information
            calendar_event = {
                'id': event['event_id'],
                'title': event['nama_event'],
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'description': event['deskripsi'],
                'status': event['status_approval'],
                'color': get_status_color(event['status_approval']),
                'textColor': '#ffffff',  # White text for better contrast
                'borderColor': get_status_border_color(event['status_approval']),
                'display': 'block',  # Show as block to make it more visible
                'allDay': True,  # Show as all-day event
                'extendedProps': {
                    'status': event['status_approval'],
                    'description': event['deskripsi'],
                    'duration': (end_date - start_date).days,
                    'isMultiDay': (end_date - start_date).days > 1
                }
            }
            calendar_events.append(calendar_event)

        return jsonify(calendar_events), 200

    except Exception as e:
        logger.error(f"Error fetching calendar events: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5013, debug=True)
