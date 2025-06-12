from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import time
import os
import requests
import logging
import graphene
from graphene import ObjectType, String, Int, Field, Mutation, List, Date
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///add_event.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Event(db.Model):
    event_id = db.Column(db.Integer, primary_key=True)
    nama_event = db.Column(db.String(255), nullable=False)
    deskripsi = db.Column(db.String(1000), nullable=False)
    tanggal_mulai = db.Column(db.Date, nullable=False)
    tanggal_selesai = db.Column(db.Date, nullable=False)
    status_approval = db.Column(db.String(255), default='Pending')

# GraphQL Types
class EventType(ObjectType):
    event_id = Int()
    nama_event = String()
    deskripsi = String()
    tanggal_mulai = String()
    tanggal_selesai = String()
    status_approval = String()

# GraphQL Mutations
class CreateEvent(Mutation):
    class Arguments:
        nama_event = String(required=True)
        deskripsi = String(required=True)
        tanggal_mulai = String(required=True)
        tanggal_selesai = String(required=True)

    event = Field(lambda: EventType)

    def mutate(self, info, nama_event, deskripsi, tanggal_mulai, tanggal_selesai):
        try:
            tanggal_mulai_date = datetime.strptime(tanggal_mulai, '%Y-%m-%d').date()
            tanggal_selesai_date = datetime.strptime(tanggal_selesai, '%Y-%m-%d').date()

            if tanggal_mulai_date >= tanggal_selesai_date:
                raise Exception('Tanggal mulai harus sebelum tanggal selesai')

            new_event = Event(
                event_id=int(datetime.now().timestamp()),
                nama_event=nama_event,
                deskripsi=deskripsi,
                tanggal_mulai=tanggal_mulai_date,
                tanggal_selesai=tanggal_selesai_date,
                status_approval='Pending'
            )
            db.session.add(new_event)
            db.session.commit()

            return CreateEvent(event=new_event)
        except Exception as e:
            raise Exception(str(e))

class UpdateEventStatus(Mutation):
    class Arguments:
        event_id = Int(required=True)
        status_approval = String(required=True)

    event = Field(lambda: EventType)

    def mutate(self, info, event_id, status_approval):
        event = Event.query.get(event_id)
        if not event:
            raise Exception("Event not found")

        event.status_approval = status_approval
        db.session.commit()
        return UpdateEventStatus(event=event)

# GraphQL Queries
class Query(ObjectType):
    events = List(EventType)
    event = Field(EventType, event_id=Int(required=True))
    approved_events = List(EventType)

    def resolve_events(self, info):
        return Event.query.all()

    def resolve_event(self, info, event_id):
        return Event.query.get(event_id)

    def resolve_approved_events(self, info):
        return Event.query.filter_by(status_approval='Approved').all()

class Mutation(ObjectType):
    create_event = CreateEvent.Field()
    update_event_status = UpdateEventStatus.Field()

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

with app.app_context():
    db.create_all()

@app.route('/api/events', methods=['POST'])
def add_event():
    try:
        data = request.json
        required_fields = ['nama_event', 'deskripsi', 'tanggal_mulai', 'tanggal_selesai']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing field: {field}'}), 400

        tanggal_mulai = datetime.strptime(data['tanggal_mulai'], '%Y-%m-%d').date()
        tanggal_selesai = datetime.strptime(data['tanggal_selesai'], '%Y-%m-%d').date()

        if tanggal_mulai >= tanggal_selesai:
            return jsonify({'error': 'Tanggal mulai harus sebelum tanggal selesai'}), 400

        new_event = Event(
            event_id=int(datetime.now().timestamp()),
            nama_event=data['nama_event'],
            deskripsi=data['deskripsi'],
            tanggal_mulai=tanggal_mulai,
            tanggal_selesai=tanggal_selesai,
            status_approval='Pending'
        )
        db.session.add(new_event)
        db.session.commit()

        return jsonify({
            'message': 'Event created successfully', 
            'event_id': new_event.event_id,
            'nama_event': new_event.nama_event,
            'deskripsi': new_event.deskripsi,
            'tanggal_mulai': new_event.tanggal_mulai.isoformat(),
            'tanggal_selesai': new_event.tanggal_selesai.isoformat(),
            'status_approval': new_event.status_approval
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/events', methods=['GET'])
def get_events():
    try:
        events = Event.query.all()
        event_list = [
            {
                'event_id': e.event_id,
                'nama_event': e.nama_event,
                'deskripsi': e.deskripsi,
                'tanggal_mulai': e.tanggal_mulai.isoformat(),
                'tanggal_selesai': e.tanggal_selesai.isoformat(),
                'status_approval': e.status_approval
            }
            for e in events
        ]
        return jsonify(event_list), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/events/<int:event_id>', methods=['GET'])
def get_event(event_id):
    try:
        event = Event.query.get(event_id)
        if not event:
            return jsonify({'error': 'Event not found'}), 404
            
        return jsonify({
            'event_id': event.event_id,
            'nama_event': event.nama_event,
            'deskripsi': event.deskripsi,
            'tanggal_mulai': event.tanggal_mulai.isoformat(),
            'tanggal_selesai': event.tanggal_selesai.isoformat(),
            'status_approval': event.status_approval
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/approved-events', methods=['GET'])
def get_approved_events():
    try:
        events = Event.query.filter_by(status_approval='Approved').all()
        event_list = [
            {
                'event_id': e.event_id,
                'nama_event': e.nama_event,
                'deskripsi': e.deskripsi,
                'tanggal_mulai': e.tanggal_mulai.isoformat(),
                'tanggal_selesai': e.tanggal_selesai.isoformat(),
                'status_approval': e.status_approval
            }
            for e in events
        ]
        return jsonify(event_list), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bookings', methods=['GET'])
def get_all_bookings():
    bookings = Booking.query.all()
    # Fetch all events and rooms once (optional optimization)
    try:
        events_resp = requests.get(f"{ADD_EVENT_SERVICE}/api/events", timeout=2)
        events_map = {e['event_id']: e['nama_event'] for e in events_resp.json()} if events_resp.status_code == 200 else {}
    except Exception as e:
        logging.error(f"Failed to fetch events: {e}")
        events_map = {}
    try:
        rooms_resp = requests.get(f"{ROOM_AVAILABILITY_SERVICE}/rooms", timeout=2)
        rooms_map = {r['room_id']: r['nama_ruangan'] for r in rooms_resp.json()} if rooms_resp.status_code == 200 else {}
    except Exception as e:
        logging.error(f"Failed to fetch rooms: {e}")
        rooms_map = {}

    results = []
    for booking in bookings:
        nama_event = events_map.get(booking.event_id, '-')
        nama_ruangan = rooms_map.get(booking.room_id, '-')
        results.append({
            'booking_id': booking.booking_id,
            'nama_event': nama_event,
            'nama_ruangan': nama_ruangan,
            'tanggal_booking': booking.tanggal_booking.strftime('%Y-%m-%d %H:%M:%S'),
            'tanggal_mulai': booking.tanggal_mulai.strftime('%Y-%m-%d'),
            'tanggal_selesai': booking.tanggal_selesai.strftime('%Y-%m-%d'),
            'status': booking.status_booking,
            'keterangan_reject': booking.keterangan_reject or ""
        })
    return jsonify(results)

@app.route('/api/events/<int:event_id>/update-status', methods=['POST'])
def update_event_status(event_id):
    try:
        data = request.json
        if not data or 'status_approval' not in data:
            return jsonify({'error': 'Missing status_approval field'}), 400
            
        event = Event.query.get(event_id)
        if not event:
            return jsonify({'error': 'Event not found'}), 404
            
        event.status_approval = data['status_approval']
        db.session.commit()
        
        return jsonify({
            'message': 'Event status updated successfully',
            'event_id': event.event_id,
            'status_approval': event.status_approval
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5008, debug=True)
