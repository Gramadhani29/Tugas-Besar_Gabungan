# File: app.py (Main Flask App)

from flask import Flask, render_template, request, jsonify
import requests
import os
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
app.secret_key = "frontend-secret-key"
CORS(app)

# Service URLs
ADD_EVENT_SERVICE = os.getenv("ADD_EVENT_SERVICE_URL", "http://add_event_service:5008")
EVENT_STATUS_SERVICE = os.getenv("EVENT_STATUS_SERVICE_URL", "http://event_status_service:5011")
ROOM_BOOKING_STATUS_SERVICE = os.getenv("ROOM_BOOKING_STATUS_SERVICE_URL", "http://localhost:5012")
EVENT_APPROVAL_SERVICE = os.getenv("EVENT_APPROVAL_SERVICE_URL", "http://event_approval_service:5010")

@app.route('/')
def index():
    return render_template('dashboard.html', current_year=datetime.now().year)

@app.route('/event')
def event_form():
    return render_template('event.html', current_year=datetime.now().year)

@app.route('/api/events', methods=['GET'])
def get_events():
    try:
        response = requests.get(f"{ADD_EVENT_SERVICE}/api/events")
        response.raise_for_status()
        events = response.json()
        
        status_response = requests.get(f"{EVENT_STATUS_SERVICE}/api/events/status")
        if status_response.status_code == 200:
            statuses = {s['event_id']: s['status'] for s in status_response.json()}
            for event in events:
                event['status_approval'] = statuses.get(event['event_id'], 'Pending')
        
        return jsonify(events), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/events', methods=['POST'])
def add_event():
    try:
        data = request.json
        required_fields = ['nama_event', 'deskripsi', 'tanggal_mulai', 'tanggal_selesai']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing field: {field}'}), 400

        response = requests.post(f"{ADD_EVENT_SERVICE}/api/events", json=data)
        response.raise_for_status()
        event_data = response.json()

        status_data = {
            'event_id': event_data['event_id'],
            'status': 'Pending'
        }
        
        status_response = requests.post(f"{EVENT_STATUS_SERVICE}/api/events/status", json=status_data)
        status_response.raise_for_status()
        
        approval_response = requests.post(f"{EVENT_APPROVAL_SERVICE}/api/events/approve", 
                                       json={'event_id': event_data['event_id'], 'status': 'Pending'})
        approval_response.raise_for_status()

        return jsonify(event_data), 201
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/events/<int:event_id>', methods=['GET'])
def get_event(event_id):
    try:
        response = requests.get(f"{ADD_EVENT_SERVICE}/api/events/{event_id}")
        response.raise_for_status()
        event = response.json()

        status_response = requests.get(f"{EVENT_STATUS_SERVICE}/api/events/{event_id}/status")
        if status_response.status_code == 200:
            status_data = status_response.json()
            event['status_approval'] = status_data.get('status_approval', 'Pending')
            event['rejection_reason'] = status_data.get('rejection_reason')

        approval_response = requests.get(f"{EVENT_APPROVAL_SERVICE}/api/events/{event_id}/approval-logs")
        if approval_response.status_code == 200:
            approval_logs = approval_response.json()
            if approval_logs:
                latest_log = approval_logs[0]
                event['status_approval'] = latest_log['status']
                if latest_log['catatan']:
                    event['rejection_reason'] = latest_log['catatan']

        return jsonify(event), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/bookings', methods=['GET'])
def get_bookings():
    try:
        response = requests.get(f"{ROOM_BOOKING_STATUS_SERVICE}/bookings")
        response.raise_for_status()
        return jsonify(response.json()), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/bookings/<event_id>', methods=['GET'])
def get_booking_by_event_id(event_id):
    try:
        response = requests.get(f"{ROOM_BOOKING_STATUS_SERVICE}/bookings/{event_id}")
        response.raise_for_status()
        return jsonify(response.json()), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5007, debug=True)