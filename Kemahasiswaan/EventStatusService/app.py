from flask import Flask, jsonify, request
import requests
import os

app = Flask(__name__)

ADD_EVENT_SERVICE = os.getenv('ADD_EVENT_SERVICE_URL', 'http://localhost:5008')
ROOM_BOOKING_STATUS_SERVICE = os.getenv('ROOM_BOOKING_STATUS_SERVICE_URL', 'http://localhost:5012')

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