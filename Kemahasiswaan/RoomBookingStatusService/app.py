import os
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import graphene
from graphene import ObjectType, String, Int, Field, List

app = Flask(__name__)
CORS(app)

# Menggunakan environment variable dengan fallback default
BOOKING_SERVICE_URL = os.getenv("BOOKING_CONFIRMATION_SERVICE_URL", "http://booking_confirmation_service:5006")
ROOM_SERVICE_URL = os.getenv("ROOM_AVAILABILITY_SERVICE_URL", "http://room_availability_service:5001")

# Konfigurasi logging
logging.basicConfig(level=logging.DEBUG)

# GraphQL Types
class RoomType(ObjectType):
    room_id = Int()
    nama_ruangan = String()
    kapasitas = Int()
    lokasi = String()

class BookingType(ObjectType):
    event_id = Int()
    room_id = Int()
    nama_ruangan = String()
    kapasitas = Int()
    lokasi = String()
    keterangan_reject = String()

# GraphQL Queries
class Query(ObjectType):
    bookings = List(BookingType)
    booking = Field(BookingType, event_id=Int(required=True))

    def resolve_bookings(self, info):
        try:
            booking_response = requests.get(f"{BOOKING_SERVICE_URL}/bookings")
            if not booking_response.ok:
                return []
            bookings = booking_response.json()
            for booking in bookings:
                room_id = booking.get('room_id')
                if room_id:
                    room_response = requests.get(f"{ROOM_SERVICE_URL}/rooms/{room_id}")
                    if room_response.ok:
                        room_data = room_response.json()
                        booking.update({
                            'nama_ruangan': room_data.get('nama_ruangan'),
                            'kapasitas': room_data.get('kapasitas'),
                            'lokasi': room_data.get('lokasi'),
                            'keterangan_reject': booking.get('keterangan_reject', '')
                        })
            return bookings
        except Exception as e:
            logging.error(f"Error in resolve_bookings: {str(e)}")
            return []

    def resolve_booking(self, info, event_id):
        try:
            booking_response = requests.get(f"{BOOKING_SERVICE_URL}/bookings")
            if not booking_response.ok:
                return None
            bookings = booking_response.json()
            booking = next((b for b in bookings if str(b.get('event_id')) == str(event_id)), None)
            if not booking:
                return None
            room_id = booking.get('room_id')
            if room_id:
                room_response = requests.get(f"{ROOM_SERVICE_URL}/rooms/{room_id}")
                if room_response.ok:
                    room_data = room_response.json()
                    booking.update({
                        'nama_ruangan': room_data.get('nama_ruangan'),
                        'kapasitas': room_data.get('kapasitas'),
                        'lokasi': room_data.get('lokasi'),
                        'keterangan_reject': booking.get('keterangan_reject', '')
                    })
            return booking
        except Exception as e:
            logging.error(f"Error in resolve_booking: {str(e)}")
            return None

schema = graphene.Schema(query=Query)

@app.route("/graphql", methods=["GET", "POST"])
def graphql():
    if request.method == "GET":
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

# Existing REST endpoints
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