# ====================
# Import Libraries
# ====================
from flask import Flask, render_template, request, jsonify, Response
import requests
import os
from ariadne import QueryType, MutationType, make_executable_schema, gql, convert_kwargs_to_snake_case
from ariadne.wsgi import GraphQL
from flask_cors import CORS
from datetime import datetime
from werkzeug.wrappers import Request

# ====================
# App Initialization
# ====================
app = Flask(__name__)
app.secret_key = "frontend-secret-key"
CORS(app) # Mengaktifkan CORS agar bisa diakses dari frontend/backend lain

# ====================
# Service Endpoint Config
# ====================
BOOKING_CONFIRMATION_SERVICE = os.getenv("BOOKING_CONFIRMATION_SERVICE_URL", "http://booking_confirmation_service:5006")
ROOM_AVAILABILITY_SERVICE = os.getenv("ROOM_AVAILABILITY_SERVICE_URL", "http://room_availability_service:5001")
ROOM_RECOMMENDATION_SERVICE = os.getenv("ROOM_RECOMMENDATION_SERVICE_URL", "http://room_recommendation_service:5002")
ROOM_BOOKING_SERVICE = os.getenv("ROOM_BOOKING_SERVICE_URL", "http://room_booking_service:5003")
ROOM_SCHEDULE_SERVICE = os.getenv("ROOM_SCHEDULE_SERVICE_URL", "http://room_schedule_service:5004")
ADD_EVENT_SERVICE = os.getenv("ADD_EVENT_SERVICE_URL", "http://add_event_service:5008")

# ====================
# Page Routes
# ====================
@app.route('/')
def index():
    return render_template('index.html', current_year=datetime.now().year)

@app.route('/approval')
def approval_page():
    try:
        resp = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings")
        bookings = resp.json() if resp.status_code == 200 else []
    except Exception:
        bookings = []
    return render_template('approval.html', bookings=bookings, current_year=datetime.now().year)

@app.route('/services')
def services_page():
    return render_template('services.html', current_year=datetime.now().year)

# ====================
# REST Endpoints
# ====================
@app.route('/api/rooms', methods=['GET'])
def get_rooms():
    try:
        response = requests.get(f"{ROOM_AVAILABILITY_SERVICE}/rooms")
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Failed to connect to Room Service"}), 503

@app.route('/api/rooms/locations', methods=['GET'])
def get_locations():
    try:
        response = requests.get(f"{ROOM_AVAILABILITY_SERVICE}/locations")
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Failed to connect to Room Service"}), 503

@app.route('/api/rooms/<int:room_id>', methods=['GET'])
def get_room_detail(room_id):
    try:
        response = requests.get(f"{ROOM_AVAILABILITY_SERVICE}/rooms/{room_id}")
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Failed to connect to Room Service"}), 503

@app.route('/api/rooms/recommend', methods=['GET'])
def get_rooms_recommend():
    try:
        params = request.args.to_dict()
        response = requests.get(f"{ROOM_RECOMMENDATION_SERVICE}/api/rooms/recommend-rooms", params=params)
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Failed to connect to Recommendation Service"}), 503

@app.route('/api/book-room', methods=['POST'])
def create_booking():
    try:
        data = request.json
        response = requests.post(f"{ROOM_BOOKING_SERVICE}/api/book-room", json=data)
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Failed to connect to Booking Service"}), 503

@app.route('/api/bookings', methods=['GET'])
def get_bookings_proxy():
    try:
        response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings")
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Failed to connect to Booking Service"}), 503

@app.route('/api/bookings/event/<int:event_id>', methods=['GET'])
def get_bookings_by_event(event_id):
    try:
        response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings/event/{event_id}")
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Failed to connect to Booking Service"}), 503

@app.route('/api/approved-events', methods=['GET'])
def get_approved_events():
    try:
        response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/approved-events")
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Failed to connect to Booking Service"}), 503

@app.route('/api/schedules/<int:room_id>', methods=['GET'])
def get_schedules(room_id):
    try:
        params = request.args.to_dict()
        response = requests.get(f"{ROOM_SCHEDULE_SERVICE}/schedules/{room_id}", params=params)
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Failed to connect to Schedule Service"}), 503

@app.route('/api/events', methods=['GET'])
def get_events():
    try:
        response = requests.get(f"{ADD_EVENT_SERVICE}/api/events")
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Failed to connect to Event Service"}), 503
    
@app.route('/api/events', methods=['POST'])
def add_event():
    try:
        data = request.json
        required_fields = ['nama_event', 'deskripsi', 'tanggal_mulai', 'tanggal_selesai']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing field: {field}'}), 400

        # Forward POST to backend service
        response = requests.post(f"{ADD_EVENT_SERVICE}/api/events", json=data)
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Failed to connect to Event Service"}), 503
    
@app.route('/api/events/<int:event_id>', methods=['GET'])
def get_event(event_id):
    try:
        response = requests.get(f"{ADD_EVENT_SERVICE}/api/events/{event_id}")
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException:
        return jsonify({"error": "Failed to connect to Event Service"}), 503

@app.route('/api/approval-status', methods=['GET'])
def get_approval_status_proxy():
    try:
        response = requests.get(f"{BOOKING_CONFIRMATION_SERVICE}/api/approval-status")
        return (response.text, response.status_code)
    except requests.exceptions.RequestException:
        return ("Offline", 503)

@app.route('/api/schedules', methods=['GET'])
def get_schedules_proxy():
    try:
        response = requests.get(f"{ROOM_SCHEDULE_SERVICE}/api/health")
        return (response.text, response.status_code)
    except requests.exceptions.RequestException:
        return ("Offline", 503)

@app.route('/api/update-booking-status/<int:booking_id>', methods=['POST'])
def update_booking_status(booking_id):
    try:
        data = request.get_json(force=True)
        # Forward ke booking_confirmation_service
        resp = requests.post(
            f"{BOOKING_CONFIRMATION_SERVICE}/api/update-booking-status/{booking_id}",
            json=data
        )
        
        if resp.status_code == 200:
            # Jika berhasil di booking_confirmation_service, update di room_booking_service
            room_booking_resp = requests.post(
                f"{ROOM_BOOKING_SERVICE}/api/update-booking-status/{booking_id}",
                json=data
            )
            if room_booking_resp.status_code != 200:
                print(f"Warning: Failed to update room booking service: {room_booking_resp.text}")
        
        return (resp.text, resp.status_code, resp.headers.items())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/bookings', methods=['GET'])
def get_bookings():
    try:
        response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings")
        if response.status_code == 200:
            return jsonify(response.json())
        return jsonify([])
    except requests.exceptions.RequestException:
        return jsonify([])

# ====================
# Run Application
# ====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, debug=True)
