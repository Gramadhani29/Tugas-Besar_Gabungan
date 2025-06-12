# =====================
# Import Libraries
# =====================
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, date
import logging
import requests
from enum import Enum

# ====================
# App Initialization
# ====================
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ====================
# Service Endpoint Config
# ====================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///booking_confirmation.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ====================
# Database Initialization
# ====================
db = SQLAlchemy(app)

# ====================
# Logging Configuration
# ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ====================
# Booking Status Enum
# ====================
class BookingStatus(str, Enum):
    PENDING = 'Pending'
    APPROVED = 'Approved'
    REJECTED = 'Rejected'

# ====================
# Booking Model
# ====================
class Booking(db.Model):
    booking_id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, nullable=False)
    room_id = db.Column(db.Integer, nullable=False)
    tanggal_booking = db.Column(db.DateTime, nullable=False)
    tanggal_mulai = db.Column(db.Date, nullable=False)
    tanggal_selesai = db.Column(db.Date, nullable=False)
    status_booking = db.Column(db.String(20), nullable=False)
    keterangan_reject = db.Column(db.String(255))

# ====================
# Approval Log Model
# ====================
class ApprovalLog(db.Model):
    approval_id = db.Column(db.Integer, primary_key=True)
    id_booking = db.Column(db.Integer, nullable=False)
    tanggal_approval = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(255), nullable=False)
    catatan = db.Column(db.String(255))

# ====================
# Create DB
# ====================
with app.app_context():
    db.create_all()

# ====================
# Routes
# ====================
@app.route('/update-booking-status/<int:booking_id>', methods=['POST'])
def update_booking_status(booking_id):
    try:
        data = request.get_json(force=True)
        logger.info("Received data: %s", data)

        if not data:
            return jsonify({'error': 'No data received'}), 400

        raw_status = data.get('status_booking')
        keterangan_reject = data.get('keterangan_reject', '').strip()

        try:
            new_status = BookingStatus(raw_status.capitalize())
        except ValueError:
            return jsonify({'error': 'Invalid status_booking value'}), 400

        booking = Booking.query.get(booking_id)
        if not booking:
            return jsonify({'error': 'Booking not found'}), 404

        if booking.status_booking != BookingStatus.PENDING:
            return jsonify({'error': 'Booking status already finalized'}), 409

        if new_status == BookingStatus.REJECTED and not keterangan_reject:
            return jsonify({'error': 'Keterangan reject wajib diisi jika status Rejected'}), 400

        booking.status_booking = new_status
        booking.keterangan_reject = keterangan_reject if new_status == BookingStatus.REJECTED else None
        db.session.commit()

        approval_log = ApprovalLog(
            id_booking=booking.booking_id,
            tanggal_approval=datetime.now(),
            status=new_status,
            catatan=keterangan_reject if new_status == BookingStatus.REJECTED else None
        )
        db.session.add(approval_log)
        db.session.commit()

        try:
            requests.post(
                f"http://room_booking_service:5003/api/update-booking-status/{booking_id}",
                json={
                    "status_booking": new_status,
                    "keterangan_reject": keterangan_reject if new_status == BookingStatus.REJECTED else ""
                },
                timeout=2
            )
        except Exception as e:
            logger.error("Failed to update status in room_booking_service: %s", str(e))

        return jsonify({
            'message': 'Booking status updated successfully',
            'booking_id': booking.booking_id,
            'new_status': booking.status_booking,
            'keterangan_reject': booking.keterangan_reject
        })

    except Exception as e:
        logger.error("Error: %s", str(e))
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/bookings', methods=['GET'])
def get_bookings():
    bookings = Booking.query.order_by(Booking.tanggal_booking.desc()).all()
    result = []
    for b in bookings:
        result.append({
            'booking_id': b.booking_id,
            'event_id': b.event_id,
            'room_id': b.room_id,
            'tanggal_booking': b.tanggal_booking.strftime('%Y-%m-%d %H:%M:%S'),
            'tanggal_mulai': b.tanggal_mulai.strftime('%Y-%m-%d'),
            'tanggal_selesai': b.tanggal_selesai.strftime('%Y-%m-%d'),
            'status_booking': b.status_booking,
            'keterangan_reject': b.keterangan_reject
        })
    return jsonify(result)

@app.route('/api/sync-booking', methods=['POST'])
def sync_booking():
    data = request.json
    if not data or 'booking_id' not in data:
        return {'error': 'Missing booking_id'}, 400
    if Booking.query.get(data['booking_id']):
        return {'message': 'Booking already exists'}, 200
    b = Booking(
        booking_id=data['booking_id'],
        event_id=data['event_id'],
        room_id=data['room_id'],
        tanggal_booking=datetime.strptime(data['tanggal_booking'], '%Y-%m-%d %H:%M:%S'),
        tanggal_mulai=datetime.strptime(data['tanggal_mulai'], '%Y-%m-%d').date(),
        tanggal_selesai=datetime.strptime(data['tanggal_selesai'], '%Y-%m-%d').date(),
        status_booking=data.get('status_booking', 'Pending'),
        keterangan_reject=data.get('keterangan_reject')
    )
    db.session.add(b)
    db.session.commit()
    logger.info("Received sync booking: %s", data)
    return {'message': 'Booking synced'}, 201

@app.route('/api/approval-status/<int:booking_id>', methods=['GET'])
def get_approval_status(booking_id):
    approval = ApprovalLog.query.filter_by(id_booking=booking_id).order_by(ApprovalLog.tanggal_approval.desc()).first()
    if not approval:
        return jsonify({'status': 'Pending', 'catatan': None}), 200
    return jsonify({
        'status': approval.status,
        'catatan': approval.catatan
    }), 200

@app.route('/booking/<int:booking_id>', methods=['GET'])
def get_booking(booking_id):
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
        'status_booking': booking.status_booking,
        'keterangan_reject': booking.keterangan_reject
    }), 200

@app.route('/api/approval-logs/<int:booking_id>', methods=['GET'])
def get_approval_logs(booking_id):
    logs = ApprovalLog.query.filter_by(id_booking=booking_id).order_by(ApprovalLog.tanggal_approval.desc()).all()
    return jsonify([
        {
            'tanggal_approval': log.tanggal_approval.strftime('%Y-%m-%d %H:%M:%S'),
            'status': log.status,
            'catatan': log.catatan
        } for log in logs
    ])

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

# ====================
# Run Application
# ====================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5006)