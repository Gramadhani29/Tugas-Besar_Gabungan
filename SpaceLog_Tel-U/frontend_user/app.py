# =====================
# Import Libraries
# =====================
from flask import Flask, render_template, request, jsonify, Response
import requests
import os
from ariadne import QueryType, MutationType, make_executable_schema, gql, convert_kwargs_to_snake_case
from ariadne.wsgi import GraphQL
from flask_cors import CORS
from datetime import datetime
from werkzeug.wrappers import Request
import graphene

# =====================
# App Initialization
# =====================
app = Flask(__name__)
app.secret_key = "frontend-secret-key"
CORS(app) # Mengaktifkan CORS agar bisa diakses dari frontend/backend lain

# =====================
# Service Endpoint Config
# =====================
ROOM_AVAILABILITY_SERVICE = os.getenv("ROOM_AVAILABILITY_SERVICE_URL", "http://room_availability_service:5001")
ROOM_RECOMMENDATION_SERVICE = os.getenv("ROOM_RECOMMENDATION_SERVICE_URL", "http://room_recommendation_service:5002")
ROOM_BOOKING_SERVICE = os.getenv("ROOM_BOOKING_SERVICE_URL", "http://room_booking_service:5003")
ROOM_SCHEDULE_SERVICE = os.getenv("ROOM_SCHEDULE_SERVICE_URL", "http://room_schedule_service:5004")
ADD_EVENT_SERVICE = os.getenv("ADD_EVENT_SERVICE_URL", "http://add_event_service:5008")

# =====================
# Page Routes
# =====================
@app.route('/')
def index():
    return render_template('index.html', current_year=datetime.now().year)

@app.route('/rooms')
def rooms_page():
    return render_template('rooms.html', current_year=datetime.now().year)

@app.route('/bookings')
def bookings_page():
    bookings = get_all_bookings()
    return render_template('bookings.html', bookings=bookings, current_year=datetime.now().year)

@app.route('/schedules')
def schedules_page():
    return render_template('schedules.html', current_year=datetime.now().year)

# =====================
# REST Endpoints
# =====================
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
def recommend_rooms():
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

@app.route('/api/bookings/<int:booking_id>', methods=['GET'])
def get_booking_status(booking_id):
    try:
        response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings/{booking_id}")
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
    
@app.route('/api/bookings', methods=['GET'])
def get_all_bookings():
    try:
        response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return []

@app.route('/api/bookings', methods=['POST'])
def create_booking_api():
    try:
        data = request.json
        print("Booking request data:", data)  # Tambahkan ini untuk cek data yang diterima
        
        if not data or 'event_id' not in data or 'room_id' not in data:
            return jsonify({'error': 'Missing required fields'}), 400
        
        response = requests.post(f"{ROOM_BOOKING_SERVICE}/api/book-room", json=data)
        print("Response from booking service:", response.status_code, response.text)  # Cek respon detail
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

# =====================
# Run Application
# =====================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)