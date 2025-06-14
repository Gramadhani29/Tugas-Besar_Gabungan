# =====================
# Import Libraries
# =====================
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import requests
from datetime import datetime, date
from enum import Enum
from marshmallow import Schema, fields, ValidationError
import pytz
import graphene
from graphene import ObjectType, String, Int, Field, Mutation

# ====================
# App Initialization
# ====================
app = Flask(__name__)
CORS(app)  # Mengaktifkan CORS agar bisa diakses dari frontend/backend lain

# ====================
# Service Endpoint Config
# ====================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///room_booking.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

ROOM_AVAILABILITY_SERVICE = "http://room_availability_service:5001"
ADD_EVENT_SERVICE = "http://add_event_service:5008"
BOOKING_CONFIRMATION_SERVICE = "http://booking_confirmation_service:5006"

# ====================
# Database Initialization
# ====================
db = SQLAlchemy(app)

# ====================
# Booking Status Enum
# ====================
class BookingStatus(str, Enum):
    PENDING = 'Pending'
    APPROVED = 'Approved'
    REJECTED = 'Rejected'

# ====================
# Model
# ====================
class Booking(db.Model):
    booking_id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer)
    room_id = db.Column(db.Integer)
    approval_id = db.Column(db.Integer)
    tanggal_booking = db.Column(db.DateTime)
    tanggal_mulai = db.Column(db.Date)
    tanggal_selesai = db.Column(db.Date)
    status_booking = db.Column(db.String(20))
    keterangan_reject = db.Column(db.String(255))

with app.app_context():
    db.create_all()

# ====================
# Marshmallow Schema for input validation
# ====================
class BookingRequestSchema(Schema):
    event_id = fields.Int(required=True)
    room_id = fields.Int(required=True)

booking_schema = BookingRequestSchema()

# ====================
# Routes
# ====================
@app.route('/api/approved-events', methods=['GET'])
def get_approved_events():
    try:
        response = requests.get(f"{ADD_EVENT_SERVICE}/api/events")
        response.raise_for_status()
        all_events = response.json()
        approved_events = [event for event in all_events if event.get('status_approval') == 'Approved']
        return jsonify(approved_events)
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Service error: {str(e)}'}), 500

@app.route('/api/book-room', methods=['POST'])
def book_room():
    try:
        data = request.get_json()
        if data is None:
            return jsonify({'error': 'Invalid JSON payload'}), 400

        booking_schema.load(data)

        event_id = data['event_id']
        room_id = data['room_id']

        event_response = requests.get(f"{ADD_EVENT_SERVICE}/api/events/{event_id}")
        if event_response.status_code != 200:
            return jsonify({'error': 'Event not found'}), 404

        event_data = event_response.json()
        tanggal_mulai = event_data.get('tanggal_mulai')
        tanggal_selesai = event_data.get('tanggal_selesai')

        if not all([tanggal_mulai, tanggal_selesai]):
            return jsonify({'error': 'Event data incomplete'}), 400

        availability_response = requests.get(
            f"{ROOM_AVAILABILITY_SERVICE}/check-availability",
            params={
                'room_id': room_id,
                'start_date': tanggal_mulai,
                'end_date': tanggal_selesai
            }
        )
        if availability_response.status_code != 200:
            return jsonify({'error': 'Failed to check room availability'}), 500

        availability = availability_response.json()
        if not availability.get('is_available', False):
            return jsonify({
                'error': 'Room is not available for the requested time slot',
                'conflicts': availability.get('conflicting_schedules', [])
            }), 409

        tanggal_mulai_dt = datetime.strptime(tanggal_mulai, "%Y-%m-%d").date()
        tanggal_selesai_dt = datetime.strptime(tanggal_selesai, "%Y-%m-%d").date()

        # Create booking in room_booking.db
        booking = Booking(
            event_id=event_id,
            room_id=room_id,
            tanggal_booking=datetime.now(pytz.timezone('Asia/Jakarta')),
            tanggal_mulai=tanggal_mulai_dt,
            tanggal_selesai=tanggal_selesai_dt,
            status_booking=BookingStatus.PENDING.value,
        )
        db.session.add(booking)
        db.session.commit()

        # Sync with booking_confirmation_service
        try:
            sync_response = requests.post(
                f"{BOOKING_CONFIRMATION_SERVICE}/api/sync-booking",
                json={
                    "booking_id": booking.booking_id,
                    "event_id": booking.event_id,
                    "room_id": booking.room_id,
                    "tanggal_booking": booking.tanggal_booking.strftime('%Y-%m-%d %H:%M:%S'),
                    "tanggal_mulai": booking.tanggal_mulai.strftime('%Y-%m-%d'),
                    "tanggal_selesai": booking.tanggal_selesai.strftime('%Y-%m-%d'),
                    "status_booking": booking.status_booking,
                    "keterangan_reject": None
                },
                timeout=2
            )
            if sync_response.status_code == 200:
                sync_data = sync_response.json()
                approval_id = sync_data.get('approval_log', {}).get('approval_id')
                if approval_id:
                    booking.approval_id = approval_id
                    db.session.commit()
            else:
                print(f"Failed to sync booking: {sync_response.text}")
        except Exception as e:
            print(f"Failed to sync booking: {e}")

        return jsonify({
            'booking_id': booking.booking_id,
            'event_id': booking.event_id,
            'status': booking.status_booking,
            'approval_id': booking.approval_id,
            'message': 'Booking created successfully'
        }), 201

    except ValidationError as err:
        return jsonify({'error': 'Validation error', 'messages': err.messages}), 400
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Service error: {str(e)}'}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Booking failed: {str(e)}'}), 500

@app.route('/api/bookings/<int:booking_id>', methods=['GET'])
def get_booking_status(booking_id):
    booking = Booking.query.get(booking_id)
    if not booking:
        return jsonify({'error': 'Booking not found'}), 404

    try:
        # Get status from booking_confirmation_service
        approval_resp = requests.get(f"{BOOKING_CONFIRMATION_SERVICE}/api/approval-status/{booking_id}", timeout=2)
        if approval_resp.status_code == 200:
            approval_data = approval_resp.json()
            status_booking = approval_data.get('status', 'Pending')
            keterangan_reject = approval_data.get('keterangan_reject')
            
            # Update local status
            booking.status_booking = status_booking
            booking.keterangan_reject = keterangan_reject
            db.session.commit()
        else:
            status_booking = 'Pending'
            keterangan_reject = None
    except Exception as e:
        print(f"Error getting approval status: {str(e)}")
        status_booking = 'Pending'
        keterangan_reject = None

    return jsonify({
        'booking_id': booking.booking_id,
        'event_id': booking.event_id,
        'room_id': booking.room_id,
        'tanggal_booking': booking.tanggal_booking.strftime('%Y-%m-%d %H:%M:%S'),
        'tanggal_mulai': booking.tanggal_mulai.strftime('%Y-%m-%d'),
        'tanggal_selesai': booking.tanggal_selesai.strftime('%Y-%m-%d'),
        'status': status_booking,
        'keterangan_reject': keterangan_reject
    })

@app.route('/api/bookings/event/<int:event_id>', methods=['GET'])
def get_bookings_by_event(event_id):
    bookings = Booking.query.filter_by(event_id=event_id).all()
    if not bookings:
        return jsonify([])

    results = []
    for booking in bookings:
        results.append({
            'booking_id': booking.booking_id,
            'event_id': booking.event_id,
            'room_id': booking.room_id,
            'tanggal_booking': booking.tanggal_booking.strftime('%Y-%m-%d %H:%M:%S'),
            'tanggal_mulai': booking.tanggal_mulai.strftime('%Y-%m-%d'),
            'tanggal_selesai': booking.tanggal_selesai.strftime('%Y-%m-%d'),
            'status': booking.status_booking,
            'keterangan_reject': booking.keterangan_reject or ""
        })
    return jsonify(results)

@app.route('/bookings/<int:booking_id>', methods=['GET'])
def get_booking_status_alias(booking_id):
    return get_booking_status(booking_id)

@app.route('/api/bookings', methods=['GET'])
def get_all_bookings():
    try:
        print("\n=== Fetching all bookings ===")
        bookings = Booking.query.all()
        print(f"Total bookings in database: {len(bookings)}")
        
        results = []
        for booking in bookings:
            try:
                print(f"\nProcessing booking {booking.booking_id}:")
                print(f"Room ID: {booking.room_id}")
                
                event_resp = requests.get(f"{ADD_EVENT_SERVICE}/api/events/{booking.event_id}")
                nama_event = event_resp.json().get('nama_event', '-') if event_resp.status_code == 200 else '-'
                print(f"Event name: {nama_event}")

                room_resp = requests.get(f"{ROOM_AVAILABILITY_SERVICE}/rooms/{booking.room_id}")
                nama_ruangan = room_resp.json().get('nama_ruangan', '-') if room_resp.status_code == 200 else '-'
                print(f"Room name: {nama_ruangan}")

                try:
                    approval_resp = requests.get(f"{BOOKING_CONFIRMATION_SERVICE}/api/approval-status/{booking.booking_id}", timeout=2)
                    approval_data = approval_resp.json() if approval_resp.status_code == 200 else {'status': 'Pending', 'keterangan_reject': None}
                    status_booking = approval_data.get('status', 'Pending')
                    keterangan_reject = approval_data.get('keterangan_reject')
                    print(f"Approval status: {status_booking}")
                except Exception as e:
                    print(f"Error getting approval status: {str(e)}")
                    status_booking = 'Pending'
                    keterangan_reject = None

                booking_data = {
                    'booking_id': booking.booking_id,
                    'nama_event': nama_event,
                    'nama_ruangan': nama_ruangan,
                    'tanggal_booking': booking.tanggal_booking.strftime('%Y-%m-%d %H:%M:%S'),
                    'tanggal_mulai': booking.tanggal_mulai.strftime('%Y-%m-%d'),
                    'tanggal_selesai': booking.tanggal_selesai.strftime('%Y-%m-%d'),
                    'status': status_booking,
                    'room_id': booking.room_id,
                    'event_id': booking.event_id,
                    'keterangan_reject': keterangan_reject
                }
                print(f"Processed booking data: {booking_data}")
                results.append(booking_data)
                
            except Exception as e:
                print(f"Error processing booking {booking.booking_id}: {str(e)}")
                continue

        print(f"\nReturning {len(results)} bookings")
        return jsonify(results)
    except Exception as e:
        print(f"Error in get_all_bookings: {str(e)}")
        return []

@app.route('/api/update-booking-status/<int:booking_id>', methods=['POST'])
def update_booking_status(booking_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        booking = Booking.query.get(booking_id)
        if not booking:
            return jsonify({'error': 'Booking not found'}), 404

        # Update booking with data from booking_confirmation_service
        if 'status_booking' in data:
            booking.status_booking = data['status_booking']
        if 'keterangan_reject' in data:
            booking.keterangan_reject = data['keterangan_reject']
        if 'approval_id' in data:
            booking.approval_id = data['approval_id']
        
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Booking status updated successfully',
            'booking': {
                'booking_id': booking.booking_id,
                'status': booking.status_booking,
                'keterangan_reject': booking.keterangan_reject,
                'approval_id': booking.approval_id
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/bookings/<int:booking_id>', methods=['DELETE'])
def delete_booking(booking_id):
    try:
        booking = Booking.query.get(booking_id)
        if not booking:
            return jsonify({'error': 'Booking not found'}), 404

        # Delete booking from database
        db.session.delete(booking)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Booking deleted successfully'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

# ====================
# GraphQL
# ====================
class BookingType(graphene.ObjectType):
    booking_id = graphene.Int()
    event_id = graphene.Int()
    room_id = graphene.Int()
    tanggal_booking = graphene.DateTime()
    tanggal_mulai = graphene.Date()
    tanggal_selesai = graphene.Date()
    status_booking = graphene.String()
    keterangan_reject = graphene.String()

    def resolve_booking_id(self, info):
        return self.booking_id

    def resolve_event_id(self, info):
        return self.event_id

    def resolve_room_id(self, info):
        return self.room_id

    def resolve_tanggal_booking(self, info):
        return self.tanggal_booking

    def resolve_tanggal_mulai(self, info):
        return self.tanggal_mulai

    def resolve_tanggal_selesai(self, info):
        return self.tanggal_selesai

    def resolve_status_booking(self, info):
        return self.status_booking

    def resolve_keterangan_reject(self, info):
        return self.keterangan_reject

# ------- Create Booking Mutation -------
class CreateBooking(graphene.Mutation):
    class Arguments:
        event_id = graphene.Int(required=True)
        room_id = graphene.Int(required=True)

    booking = graphene.Field(BookingType)
    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, event_id, room_id):
        try:
            # Check event existence
            event_response = requests.get(f"{ADD_EVENT_SERVICE}/api/events/{event_id}")
            if event_response.status_code != 200:
                return CreateBooking(success=False, message="Event not found")

            event_data = event_response.json()
            tanggal_mulai = event_data.get('tanggal_mulai')
            tanggal_selesai = event_data.get('tanggal_selesai')

            if not all([tanggal_mulai, tanggal_selesai]):
                return CreateBooking(success=False, message="Event data incomplete")

            # Check room availability
            availability_response = requests.get(
                f"{ROOM_AVAILABILITY_SERVICE}/check-availability",
                params={
                    'room_id': room_id,
                    'start_date': tanggal_mulai,
                    'end_date': tanggal_selesai
                }
            )
            
            if availability_response.status_code != 200:
                return CreateBooking(success=False, message="Failed to check room availability")

            availability = availability_response.json()
            if not availability.get('is_available', False):
                return CreateBooking(
                    success=False, 
                    message="Room is not available for the requested time slot"
                )

            # Create booking
            booking = Booking(
                event_id=event_id,
                room_id=room_id,
                tanggal_booking=datetime.now(pytz.timezone('Asia/Jakarta')),
                tanggal_mulai=datetime.strptime(tanggal_mulai, "%Y-%m-%d").date(),
                tanggal_selesai=datetime.strptime(tanggal_selesai, "%Y-%m-%d").date(),
                status_booking=BookingStatus.PENDING.value
            )
            db.session.add(booking)
            db.session.commit()

            # Sync with booking_confirmation_service
            try:
                sync_response = requests.post(
                    f"{BOOKING_CONFIRMATION_SERVICE}/api/sync-booking",
                    json={
                        "booking_id": booking.booking_id,
                        "event_id": booking.event_id,
                        "room_id": booking.room_id,
                        "tanggal_booking": booking.tanggal_booking.strftime('%Y-%m-%d %H:%M:%S'),
                        "tanggal_mulai": booking.tanggal_mulai.strftime('%Y-%m-%d'),
                        "tanggal_selesai": booking.tanggal_selesai.strftime('%Y-%m-%d'),
                        "status_booking": booking.status_booking,
                        "keterangan_reject": None
                    },
                    timeout=2
                )
                if sync_response.status_code == 200:
                    sync_data = sync_response.json()
                    approval_id = sync_data.get('approval_log', {}).get('approval_id')
                    if approval_id:
                        booking.approval_id = approval_id
                        db.session.commit()
                else:
                    print(f"Failed to sync booking: {sync_response.text}")
            except Exception as e:
                print(f"Failed to sync booking: {e}")

            return CreateBooking(
                booking=booking,
                success=True,
                message="Booking created successfully"
            )

        except Exception as e:
            db.session.rollback()
            return CreateBooking(success=False, message=str(e))

# ------- Delete Booking Mutation -------
class DeleteBooking(graphene.Mutation):
    class Arguments:
        booking_id = graphene.Int(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, booking_id):
        try:
            booking = Booking.query.get(booking_id)
            if not booking:
                return DeleteBooking(success=False, message="Booking not found")

            db.session.delete(booking)
            db.session.commit()

            return DeleteBooking(
                success=True,
                message="Booking deleted successfully"
            )

        except Exception as e:
            db.session.rollback()
            return DeleteBooking(success=False, message=str(e))

# ------- Query --------
class Query(graphene.ObjectType):
    bookings = graphene.List(BookingType)
    booking = graphene.Field(BookingType, booking_id=graphene.Int(required=True))

    def resolve_bookings(self, info):
        bookings = Booking.query.all()
        results = []
        for booking in bookings:
            try:
                approval_resp = requests.get(f"{BOOKING_CONFIRMATION_SERVICE}/api/approval-status/{booking.booking_id}", timeout=2)
                approval_data = approval_resp.json() if approval_resp.status_code == 200 else {'status': 'Pending', 'keterangan_reject': None}
                status_booking = approval_data.get('status', 'Pending')
                keterangan_reject = approval_data.get('keterangan_reject')
            except Exception as e:
                print(f"Error getting approval status: {str(e)}")
                status_booking = 'Pending'
                keterangan_reject = None

            results.append(BookingType(
                booking_id=booking.booking_id,
                event_id=booking.event_id,
                room_id=booking.room_id,
                tanggal_booking=booking.tanggal_booking,
                tanggal_mulai=booking.tanggal_mulai,
                tanggal_selesai=booking.tanggal_selesai,
                status_booking=status_booking,
                keterangan_reject=keterangan_reject
            ))
        return results

    def resolve_booking(self, info, booking_id):
        booking = Booking.query.get(booking_id)
        if not booking:
            return None

        try:
            approval_resp = requests.get(f"{BOOKING_CONFIRMATION_SERVICE}/api/approval-status/{booking_id}", timeout=2)
            approval_data = approval_resp.json() if approval_resp.status_code == 200 else {'status': 'Pending', 'keterangan_reject': None}
            status_booking = approval_data.get('status', 'Pending')
            keterangan_reject = approval_data.get('keterangan_reject')
        except Exception as e:
            print(f"Error getting approval status: {str(e)}")
            status_booking = 'Pending'
            keterangan_reject = None

        return BookingType(
            booking_id=booking.booking_id,
            event_id=booking.event_id,
            room_id=booking.room_id,
            tanggal_booking=booking.tanggal_booking,
            tanggal_mulai=booking.tanggal_mulai,
            tanggal_selesai=booking.tanggal_selesai,
            status_booking=status_booking,
            keterangan_reject=keterangan_reject
        )

class Mutation(graphene.ObjectType):
    create_booking = CreateBooking.Field()
    delete_booking = DeleteBooking.Field()

schema = graphene.Schema(query=Query, mutation=Mutation)

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

# ====================
# Run app
# ====================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)