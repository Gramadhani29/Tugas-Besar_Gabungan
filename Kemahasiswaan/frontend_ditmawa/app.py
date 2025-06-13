from flask import Flask, render_template, request, jsonify
import requests
import os
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
app.secret_key = "frontend-ditmawa-secret-key"
CORS(app)

# Service URLs
ADD_EVENT_SERVICE = os.getenv("ADD_EVENT_SERVICE_URL", "http://add_event_service:5008")
EVENT_APPROVAL_SERVICE = os.getenv("EVENT_APPROVAL_SERVICE_URL", "http://event_approval_service:5010")
EVENT_STATUS_SERVICE = os.getenv("EVENT_STATUS_SERVICE_URL", "http://event_status_service:5011")
ROOM_BOOKING_STATUS_SERVICE = os.getenv("ROOM_BOOKING_STATUS_SERVICE_URL", "http://room_booking_status_service:5012")
CALENDAR_EVENT_SERVICE = os.getenv("CALENDAR_EVENT_SERVICE_URL", "http://calendar_event_service:5013")

@app.route('/')
def index():
    return render_template('dashboard.html', current_year=datetime.now().year)

@app.route('/api/events', methods=['GET'])
def get_events():
    try:
        # Get all events
        response = requests.get(f"{ADD_EVENT_SERVICE}/api/events")
        response.raise_for_status()
        events = response.json()

        # Get event statuses
        status_response = requests.get(f"{EVENT_STATUS_SERVICE}/api/events/status")
        if status_response.status_code == 200:
            statuses = {s['event_id']: s for s in status_response.json()}
            for event in events:
                status_data = statuses.get(event['event_id'], {})
                event['status_approval'] = status_data.get('status', 'Pending')
                event['rejection_reason'] = status_data.get('rejection_reason')

        return jsonify(events), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/events/pending', methods=['GET'])
def get_pending_events():
    try:
        # Get all events
        response = requests.get(f"{ADD_EVENT_SERVICE}/api/events")
        response.raise_for_status()
        events = response.json()

        # Get event statuses
        status_response = requests.get(f"{EVENT_STATUS_SERVICE}/api/events/status")
        if status_response.status_code == 200:
            statuses = {s['event_id']: s for s in status_response.json()}
            # Filter only pending events
            pending_events = []
            for event in events:
                status_data = statuses.get(event['event_id'], {})
                if status_data.get('status') == 'Pending':
                    event['status_approval'] = 'Pending'
                    event['rejection_reason'] = status_data.get('rejection_reason')
                    pending_events.append(event)

            return jsonify(pending_events), 200
        else:
            return jsonify([]), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/events/<int:event_id>', methods=['GET'])
def get_event(event_id):
    try:
        # Get event details
        response = requests.get(f"{ADD_EVENT_SERVICE}/api/events/{event_id}")
        response.raise_for_status()
        event = response.json()

        # Get event status
        status_response = requests.get(f"{EVENT_STATUS_SERVICE}/api/events/{event_id}/status")
        if status_response.status_code == 200:
            status_data = status_response.json()
            event['status_approval'] = status_data.get('status', 'Pending')
            event['rejection_reason'] = status_data.get('rejection_reason')

        return jsonify(event), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/events/<int:event_id>/approve', methods=['POST'])
def approve_event(event_id):
    try:
        data = request.json
        if 'status' not in data:
            return jsonify({"error": "Status is required"}), 400

        # Update event status
        status_data = {
            'event_id': event_id,
            'status': data['status'],
            'rejection_reason': data.get('reason') if data['status'] == 'Rejected' else None
        }
        
        response = requests.post(f"{EVENT_APPROVAL_SERVICE}/api/events/approve", json=status_data)
        response.raise_for_status()

        # If approved, update event status
        if data['status'] == 'Approved':
            requests.post(f"{EVENT_STATUS_SERVICE}/api/events/status", json=status_data)

        return jsonify({"message": "Event status updated successfully"}), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/events/<int:event_id>/reject', methods=['POST'])
def reject_event(event_id):
    try:
        data = request.json
        if 'status' not in data or data['status'] != 'Rejected':
            return jsonify({"error": "Status must be 'Rejected'"}), 400
        if 'rejection_reason' not in data:
            return jsonify({"error": "Rejection reason is required"}), 400

        # Update event status
        status_data = {
            'event_id': event_id,
            'status': 'Rejected',
            'rejection_reason': data['rejection_reason']
        }
        response = requests.post(f"{EVENT_APPROVAL_SERVICE}/api/events/approve", json=status_data)
        response.raise_for_status()
        requests.post(f"{EVENT_STATUS_SERVICE}/api/events/status", json=status_data)
        return jsonify({"message": "Event rejected successfully"}), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/bookings', methods=['GET'])
def get_bookings():
    try:
        # Get bookings from booking status service
        response = requests.get(f"{ROOM_BOOKING_STATUS_SERVICE}/api/bookings")
        response.raise_for_status()
        bookings = response.json()

        # Get event details for each booking
        for booking in bookings:
            if 'event_id' in booking:
                event_response = requests.get(f"{ADD_EVENT_SERVICE}/api/events/{booking['event_id']}")
                if event_response.status_code == 200:
                    event_data = event_response.json()
                    booking['nama_event'] = event_data.get('nama_event', 'Unknown Event')
                    booking['status_approval'] = event_data.get('status_approval', 'Pending')

        return jsonify(bookings), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/bookings/<int:booking_id>', methods=['GET'])
def get_booking(booking_id):
    try:
        response = requests.get(f"{ROOM_BOOKING_STATUS_SERVICE}/api/bookings/{booking_id}")
        response.raise_for_status()
        booking = response.json()

        # Get event details
        if 'event_id' in booking:
            event_response = requests.get(f"{ADD_EVENT_SERVICE}/api/events/{booking['event_id']}")
            if event_response.status_code == 200:
                event_data = event_response.json()
                booking['nama_event'] = event_data.get('nama_event', 'Unknown Event')
                booking['deskripsi'] = event_data.get('deskripsi')
                booking['status_approval'] = event_data.get('status_approval', 'Pending')

        return jsonify(booking), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/calendar-events', methods=['GET'])
def get_calendar_events():
    try:
        # Forward the request to calendar service
        response = requests.get(f"{CALENDAR_EVENT_SERVICE}/api/calendar-events", params=request.args)
        response.raise_for_status()
        return jsonify(response.json()), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5009, debug=True) 