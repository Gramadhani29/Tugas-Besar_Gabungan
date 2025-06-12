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
        approved_events = [event for event in all_events if event.get('status') == 'Approved']
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

        booking = Booking(
            event_id=event_id,
            room_id=room_id,
            tanggal_booking=datetime.now(),
            tanggal_mulai=tanggal_mulai_dt,
            tanggal_selesai=tanggal_selesai_dt,
            status_booking=BookingStatus.PENDING.value,
        )
        db.session.add(booking)
        db.session.commit()

        try:
            sync_response = requests.post(
                "http://booking_confirmation_service:5006/api/sync-booking",
                json={
                    "booking_id": booking.booking_id,
                    "event_id": booking.event_id,
                    "room_id": booking.room_id,
                    "tanggal_booking": booking.tanggal_booking.strftime('%Y-%m-%d %H:%M:%S'),
                    "tanggal_mulai": booking.tanggal_mulai.strftime('%Y-%m-%d'),
                    "tanggal_selesai": booking.tanggal_selesai.strftime('%Y-%m-%d'),
                    "status_booking": booking.status_booking,
                    "keterangan_reject": booking.keterangan_reject
                },
                timeout=2
            )
            print("Sync booking response:", sync_response.status_code, sync_response.text)
        except Exception as e:
            print(f"Failed to sync booking: {e}")

        return jsonify({
            'booking_id': booking.booking_id,
            'event_id': booking.event_id,
            'status': booking.status_booking,
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

    return jsonify({
        'booking_id': booking.booking_id,
        'event_id': booking.event_id,
        'room_id': booking.room_id,
        'tanggal_booking': booking.tanggal_booking.strftime('%Y-%m-%d %H:%M:%S'),
        'tanggal_mulai': booking.tanggal_mulai.strftime('%Y-%m-%d'),
        'tanggal_selesai': booking.tanggal_selesai.strftime('%Y-%m-%d'),
        'status': booking.status_booking,
        'keterangan_reject': booking.keterangan_reject or ""
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
                print(f"Room ID: {booking.room_id}, Status: {booking.status_booking}")
                
                event_resp = requests.get(f"{ADD_EVENT_SERVICE}/api/events/{booking.event_id}")
                nama_event = event_resp.json().get('nama_event', '-') if event_resp.status_code == 200 else '-'
                print(f"Event name: {nama_event}")

                room_resp = requests.get(f"{ROOM_AVAILABILITY_SERVICE}/rooms/{booking.room_id}")
                nama_ruangan = room_resp.json().get('nama_ruangan', '-') if room_resp.status_code == 200 else '-'
                print(f"Room name: {nama_ruangan}")

                try:
                    approval_resp = requests.get(f"http://booking_confirmation_service:5006/api/approval-status/{booking.booking_id}", timeout=2)
                    status_booking = approval_resp.json().get('status', booking.status_booking) if approval_resp.status_code == 200 else booking.status_booking
                    print(f"Approval status: {status_booking}")
                except Exception as e:
                    print(f"Error getting approval status: {str(e)}")
                    status_booking = booking.status_booking

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
                    'keterangan_reject': booking.keterangan_reject or ""
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
        data = request.get_json(force=True)
        new_status = data.get('status_booking')
        keterangan_reject = data.get('keterangan_reject', '')

        if not new_status:
            return jsonify({'error': 'Missing status_booking field'}), 400

        booking = Booking.query.get(booking_id)
        if not booking:
            return jsonify({'error': 'Booking not found'}), 404

        if booking.status_booking != BookingStatus.PENDING.value:
            return jsonify({'error': 'Booking status already finalized'}), 400

        if new_status not in [BookingStatus.APPROVED.value, BookingStatus.REJECTED.value, BookingStatus.PENDING.value]:
            return jsonify({'error': 'Invalid status_booking value'}), 400

        if new_status == BookingStatus.REJECTED.value and not keterangan_reject:
            return jsonify({'error': 'Keterangan reject wajib diisi jika status Rejected'}), 400

        booking.status_booking = new_status
        booking.keterangan_reject = keterangan_reject if new_status == BookingStatus.REJECTED.value else None
        db.session.commit()

        return jsonify({'message': 'Booking status updated successfully'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

# ====================
# Run app
# ====================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)