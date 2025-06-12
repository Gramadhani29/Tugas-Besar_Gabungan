import os
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

# Menggunakan environment variable dengan fallback default
BOOKING_SERVICE_URL = os.getenv("BOOKING_CONFIRMATION_SERVICE_URL", "http://booking_confirmation_service:5006")
ROOM_SERVICE_URL = os.getenv("ROOM_AVAILABILITY_SERVICE_URL", "http://room_availability_service:5001")

# Konfigurasi logging
logging.basicConfig(level=logging.DEBUG)

@app.route('/bookings', methods=['GET'])
def get_bookings():
    logging.debug("Mengakses endpoint /bookings")
    try:
        booking_response = requests.get(f"{BOOKING_SERVICE_URL}/bookings")
        logging.debug(f"Status code dari booking service: {booking_response.status_code}")
        logging.debug(f"Respon dari booking service: {booking_response.text}")
        if not booking_response.ok:
            return jsonify({"error": "Failed to fetch bookings"}), 500
        bookings = booking_response.json()
        for booking in bookings:
            room_id = booking.get('room_id')
            if room_id:
                room_response = requests.get(f"{ROOM_SERVICE_URL}/rooms/{room_id}")
                logging.debug(f"Respon dari room service untuk room_id {room_id}: {room_response.status_code}")
                if room_response.ok:
                    room_data = room_response.json()
                    booking.update({
                        'nama_ruangan': room_data.get('nama_ruangan'),
                        'kapasitas': room_data.get('kapasitas'),
                        'lokasi': room_data.get('lokasi'),
                        'keterangan_reject': booking.get('keterangan_reject', '')
                    })
        return jsonify(bookings)
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/bookings/<event_id>', methods=['GET'])
def get_booking_by_event_id(event_id):
    logging.debug(f"Mengakses endpoint /bookings/{event_id}")
    try:
        booking_response = requests.get(f"{BOOKING_SERVICE_URL}/bookings")
        logging.debug(f"Status code dari booking service: {booking_response.status_code}")
        logging.debug(f"Respon dari booking service: {booking_response.text}")
        if not booking_response.ok:
            return jsonify({"error": "Failed to fetch bookings"}), 500
        bookings = booking_response.json()
        booking = next((b for b in bookings if str(b.get('event_id')) == str(event_id)), None)
        if not booking:
            return jsonify({"error": "Booking not found"}), 404
        room_id = booking.get('room_id')
        if room_id:
            room_response = requests.get(f"{ROOM_SERVICE_URL}/rooms/{room_id}")
            logging.debug(f"Respon dari room service untuk room_id {room_id}: {room_response.status_code}")
            if room_response.ok:
                room_data = room_response.json()
                booking.update({
                    'nama_ruangan': room_data.get('nama_ruangan'),
                    'kapasitas': room_data.get('kapasitas'),
                    'lokasi': room_data.get('lokasi'),
                    'keterangan_reject': booking.get('keterangan_reject', '')
                })
        return jsonify(booking)
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5012)