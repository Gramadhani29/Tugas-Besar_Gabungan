# ====================
# Import Libraries
# ====================
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import requests
from enum import Enum
import graphene
from graphene import ObjectType, String, Int, Field, List, Mutation

# ====================
# App Initialization
# ====================
app = Flask(__name__)
CORS(app)  # Mengaktifkan CORS agar bisa diakses dari frontend/backend lain

# ====================
# Service Endpoint Config
# ====================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///room_schedule.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

ROOM_AVAILABILITY_SERVICE = "http://room_availability_service:5001"
BOOKING_CONFIRMATION_SERVICE = "http://booking_confirmation_service:5006"
ROOM_BOOKING_SERVICE = "http://room_booking_service:5003"
ADD_EVENT_SERVICE = "http://add_event_service:5008"

# ====================
# Database Initialization
# ====================
db = SQLAlchemy(app)
DATE_FORMAT = '%Y-%m-%d'

# ====================
# Model
# ====================
class RoomSchedule(db.Model):
    schedule_id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, nullable=False)
    tanggal_mulai = db.Column(db.DateTime, nullable=False)
    tanggal_selesai = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(255), nullable=False)
    event_id = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f'<Schedule {self.schedule_id} | Room {self.room_id} | Event {self.event_id}>'

# ====================
# Create DB
# ====================
with app.app_context():
    db.create_all()

# ====================
# REST Endpoints
# ====================
@app.route('/schedules/<int:room_id>', methods=['GET'])
def get_room_schedules(room_id):
    try:
        print(f"\n=== Fetching schedules for room {room_id} ===")
        
        # Get all bookings for the room from room_booking_service
        bookings_response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings")
        print(f"Bookings response status: {bookings_response.status_code}")
        
        if bookings_response.status_code != 200:
            print(f"Error response from booking service: {bookings_response.text}")
            return jsonify({'error': 'Failed to fetch bookings'}), 500

        all_bookings = bookings_response.json()
        print(f"Total bookings received: {len(all_bookings)}")
        print(f"Sample booking data: {all_bookings[0] if all_bookings else 'No bookings'}")
        
        # Filter bookings for this room and approved status
        room_bookings = [
            b for b in all_bookings 
            if str(b.get('room_id')) == str(room_id) and b.get('status') == 'Approved'
        ]
        print(f"Filtered bookings for room {room_id}: {len(room_bookings)}")
        print(f"Filtered bookings data: {room_bookings}")
        
        if not room_bookings:
            print(f"No approved bookings found for room {room_id}")
            return jsonify({'message': 'Tidak ada jadwal yang disetujui untuk ruangan ini.'}), 200

        results = []
        for booking in room_bookings:
            try:
                print(f"\nProcessing booking: {booking}")
                
                # Get event details from add_event_service
                event_response = requests.get(
                    f"{ADD_EVENT_SERVICE}/api/events/{booking['event_id']}",
                    timeout=2
                )
                event_data = event_response.json() if event_response.status_code == 200 else {}
                print(f"Event data: {event_data}")

                # Get room details
                room_response = requests.get(
                    f"{ROOM_AVAILABILITY_SERVICE}/rooms/{room_id}",
                    timeout=2
                )
                room_data = room_response.json() if room_response.status_code == 200 else {}
                print(f"Room data: {room_data}")

                schedule_data = {
                    'booking_id': booking['booking_id'],
                    'room_id': booking['room_id'],
                    'room_name': room_data.get('nama_ruangan', 'Unknown Room'),
                    'event_id': booking['event_id'],
                    'event_name': event_data.get('nama_event', 'Unknown Event'),
                    'tanggal_mulai': booking['tanggal_mulai'],
                    'tanggal_selesai': booking['tanggal_selesai'],
                    'status': booking['status']
                }
                print(f"Processed schedule data: {schedule_data}")
                results.append(schedule_data)
                
            except requests.exceptions.RequestException as e:
                print(f"Error fetching additional data: {str(e)}")
                # Fallback jika service error
                results.append({
                    'booking_id': booking['booking_id'],
                    'room_id': booking['room_id'],
                    'room_name': 'Unknown Room',
                    'event_id': booking['event_id'],
                    'event_name': 'Unknown Event',
                    'tanggal_mulai': booking['tanggal_mulai'],
                    'tanggal_selesai': booking['tanggal_selesai'],
                    'status': booking['status']
                })

        print(f"\nFinal results: {results}")
        return jsonify(results), 200

    except Exception as e:
        print(f"Error in get_room_schedules: {str(e)}")
        return jsonify({'error': f'Failed to fetch schedules: {str(e)}'}), 500

# Add Schedule Endpoint (for internal use by booking confirmation service)
@app.route('/add-schedule', methods=['POST'])
def add_schedule():
    data = request.json
    required_fields = ['room_id', 'event_id', 'tanggal_mulai', 'tanggal_selesai', 'status']
    
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        tanggal_mulai = datetime.strptime(data['tanggal_mulai'], DATE_FORMAT)
        tanggal_selesai = datetime.strptime(data['tanggal_selesai'], DATE_FORMAT)

        if tanggal_mulai >= tanggal_selesai:
            return jsonify({'error': 'Start time must be before end time'}), 400

        # Cek konflik hanya jika status = 'Approved'
        if data['status'] == 'Approved':
            conflicts = RoomSchedule.query.filter(
                RoomSchedule.room_id == data['room_id'],
                RoomSchedule.status == 'Approved',
                RoomSchedule.tanggal_selesai > tanggal_mulai,
                RoomSchedule.tanggal_mulai < tanggal_selesai
            ).all()

            if conflicts:
                return jsonify({
                    'error': 'Schedule conflict detected with approved schedules',
                    'conflicts': [{
                        'schedule_id': c.schedule_id,
                        'event_id': c.event_id,
                        'tanggal_mulai': c.tanggal_mulai.strftime(DATE_FORMAT),
                        'tanggal_selesai': c.tanggal_selesai.strftime(DATE_FORMAT)
                    } for c in conflicts]
                }), 409

        new_schedule = RoomSchedule(
            room_id=data['room_id'],
            event_id=data['event_id'],
            tanggal_mulai=tanggal_mulai,
            tanggal_selesai=tanggal_selesai,
            status=data['status']
        )

        db.session.add(new_schedule)
        db.session.commit()

        return jsonify({
            'schedule_id': new_schedule.schedule_id,
            'message': 'Schedule added successfully'
        }), 201

    except ValueError as e:
        return jsonify({'error': f'Invalid date format: {str(e)}'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to add schedule: {str(e)}'}), 500

# Update Schedule
@app.route('/update-schedule/<int:schedule_id>', methods=['PUT'])
def update_schedule(schedule_id):
    data = request.json
    schedule = RoomSchedule.query.get(schedule_id)

    if not schedule:
        return jsonify({'error': 'Schedule not found'}), 404

    try:
        # Backup nilai sebelumnya
        old_start = schedule.tanggal_mulai
        old_end = schedule.tanggal_selesai
        old_status = schedule.status

        # Update field yang diubah
        if 'tanggal_mulai' in data:
            schedule.tanggal_mulai = datetime.strptime(data['tanggal_mulai'], DATE_FORMAT)
        if 'tanggal_selesai' in data:
            schedule.tanggal_selesai = datetime.strptime(data['tanggal_selesai'], DATE_FORMAT)
        if 'status' in data:
            schedule.status = data['status']

        if schedule.tanggal_mulai >= schedule.tanggal_selesai:
            return jsonify({'error': 'Start time must be before end time'}), 400

        # Cek konflik jika status baru adalah Approved
        if schedule.status == 'Approved':
            conflicts = RoomSchedule.query.filter(
                RoomSchedule.schedule_id != schedule.schedule_id,
                RoomSchedule.room_id == schedule.room_id,
                RoomSchedule.status == 'Approved',
                RoomSchedule.tanggal_selesai > schedule.tanggal_mulai,
                RoomSchedule.tanggal_mulai < schedule.tanggal_selesai
            ).all()

            if conflicts:
                return jsonify({
                    'error': 'Schedule conflict detected with approved schedules',
                    'conflicts': [{
                        'schedule_id': c.schedule_id,
                        'event_id': c.event_id,
                        'tanggal_mulai': c.tanggal_mulai.strftime(DATE_FORMAT),
                        'tanggal_selesai': c.tanggal_selesai.strftime(DATE_FORMAT)
                    } for c in conflicts]
                }), 409

        db.session.commit()
        return jsonify({
            'schedule_id': schedule.schedule_id,
            'message': 'Schedule updated successfully'
        }), 200

    except ValueError as e:
        return jsonify({'error': f'Invalid date format: {str(e)}'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to update schedule: {str(e)}'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

# ====================
# GraphQL
# ====================
class RoomScheduleType(ObjectType):
    schedule_id = Int()
    room_id = Int()
    event_id = Int()
    tanggal_mulai = String()
    tanggal_selesai = String()
    status = String()
    room_name = String()
    event_name = String()
    booking_id = Int()

class Query(ObjectType):
    approved_schedules = graphene.List(RoomScheduleType)
    approved_schedule = graphene.Field(RoomScheduleType, booking_id=graphene.Int(required=True))
    room_schedules = graphene.List(RoomScheduleType, room_id=graphene.Int(required=True))

    def resolve_approved_schedules(self, info):
        try:
            # Get all bookings from room_booking_service
            bookings_response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings")
            if bookings_response.status_code != 200:
                return []

            all_bookings = bookings_response.json()
            
            # Filter approved bookings
            approved_bookings = [b for b in all_bookings if b.get('status') == 'Approved']
            
            results = []
            for booking in approved_bookings:
                try:
                    # Get event details
                    event_response = requests.get(
                        f"{ADD_EVENT_SERVICE}/api/events/{booking['event_id']}",
                        timeout=2
                    )
                    event_data = event_response.json() if event_response.status_code == 200 else {}

                    # Get room details
                    room_response = requests.get(
                        f"{ROOM_AVAILABILITY_SERVICE}/rooms/{booking['room_id']}",
                        timeout=2
                    )
                    room_data = room_response.json() if room_response.status_code == 200 else {}

                    schedule_data = {
                        'booking_id': booking['booking_id'],
                        'room_id': booking['room_id'],
                        'room_name': room_data.get('nama_ruangan', 'Unknown Room'),
                        'event_id': booking['event_id'],
                        'event_name': event_data.get('nama_event', 'Unknown Event'),
                        'tanggal_mulai': booking['tanggal_mulai'],
                        'tanggal_selesai': booking['tanggal_selesai'],
                        'status': booking['status']
                    }
                    results.append(schedule_data)
                    
                except requests.exceptions.RequestException:
                    # Fallback if service error
                    results.append({
                        'booking_id': booking['booking_id'],
                        'room_id': booking['room_id'],
                        'room_name': 'Unknown Room',
                        'event_id': booking['event_id'],
                        'event_name': 'Unknown Event',
                        'tanggal_mulai': booking['tanggal_mulai'],
                        'tanggal_selesai': booking['tanggal_selesai'],
                        'status': booking['status']
                    })

            return results

        except Exception as e:
            return []

    def resolve_approved_schedule(self, info, booking_id):
        try:
            # Get booking from room_booking_service
            booking_response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings/{booking_id}")
            if booking_response.status_code != 200:
                return None

            booking = booking_response.json()
            
            # Check if booking is approved
            if booking.get('status') != 'Approved':
                return None

            try:
                # Get event details
                event_response = requests.get(
                    f"{ADD_EVENT_SERVICE}/api/events/{booking['event_id']}",
                    timeout=2
                )
                event_data = event_response.json() if event_response.status_code == 200 else {}

                # Get room details
                room_response = requests.get(
                    f"{ROOM_AVAILABILITY_SERVICE}/rooms/{booking['room_id']}",
                    timeout=2
                )
                room_data = room_response.json() if room_response.status_code == 200 else {}

                return {
                    'booking_id': booking['booking_id'],
                    'room_id': booking['room_id'],
                    'room_name': room_data.get('nama_ruangan', 'Unknown Room'),
                    'event_id': booking['event_id'],
                    'event_name': event_data.get('nama_event', 'Unknown Event'),
                    'tanggal_mulai': booking['tanggal_mulai'],
                    'tanggal_selesai': booking['tanggal_selesai'],
                    'status': booking['status']
                }
                
            except requests.exceptions.RequestException:
                # Fallback if service error
                return {
                    'booking_id': booking['booking_id'],
                    'room_id': booking['room_id'],
                    'room_name': 'Unknown Room',
                    'event_id': booking['event_id'],
                    'event_name': 'Unknown Event',
                    'tanggal_mulai': booking['tanggal_mulai'],
                    'tanggal_selesai': booking['tanggal_selesai'],
                    'status': booking['status']
                }

        except Exception as e:
            return None

    def resolve_room_schedules(self, info, room_id):
        try:
            # Get all bookings from room_booking_service
            bookings_response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings")
            if bookings_response.status_code != 200:
                return []

            all_bookings = bookings_response.json()
            
            # Filter bookings for this room and approved status
            room_bookings = [
                b for b in all_bookings 
                if str(b.get('room_id')) == str(room_id) and b.get('status') == 'Approved'
            ]
            
            results = []
            for booking in room_bookings:
                try:
                    # Get event details
                    event_response = requests.get(
                        f"{ADD_EVENT_SERVICE}/api/events/{booking['event_id']}",
                        timeout=2
                    )
                    event_data = event_response.json() if event_response.status_code == 200 else {}

                    # Get room details
                    room_response = requests.get(
                        f"{ROOM_AVAILABILITY_SERVICE}/rooms/{room_id}",
                        timeout=2
                    )
                    room_data = room_response.json() if room_response.status_code == 200 else {}

                    schedule_data = {
                        'booking_id': booking['booking_id'],
                        'room_id': booking['room_id'],
                        'room_name': room_data.get('nama_ruangan', 'Unknown Room'),
                        'event_id': booking['event_id'],
                        'event_name': event_data.get('nama_event', 'Unknown Event'),
                        'tanggal_mulai': booking['tanggal_mulai'],
                        'tanggal_selesai': booking['tanggal_selesai'],
                        'status': booking['status']
                    }
                    results.append(schedule_data)
                    
                except requests.exceptions.RequestException:
                    # Fallback if service error
                    results.append({
                        'booking_id': booking['booking_id'],
                        'room_id': booking['room_id'],
                        'room_name': 'Unknown Room',
                        'event_id': booking['event_id'],
                        'event_name': 'Unknown Event',
                        'tanggal_mulai': booking['tanggal_mulai'],
                        'tanggal_selesai': booking['tanggal_selesai'],
                        'status': booking['status']
                    })

            return results

        except Exception as e:
            print(f"Error in resolve_room_schedules: {str(e)}")
            return []

schema = graphene.Schema(query=Query)

@app.route("/graphql", methods=["GET", "POST"])
def graphql():
    if request.method == "GET":
        # Optional: serve simple GraphiQL UI for testing
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

# =====================
# Run Application
# =====================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5004)
