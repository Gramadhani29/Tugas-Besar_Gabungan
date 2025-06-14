# ====================
# Import Libraries
# ====================
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import graphene
from graphene import ObjectType, String, Int, Field, List, Schema

# ====================
# App Initialization
# ====================
app = Flask(__name__)
CORS(app)  # Mengaktifkan CORS agar bisa diakses dari frontend/backend lain

# ====================
# Service Endpoint Config
# ====================
ROOM_AVAILABILITY_SERVICE = "http://room_availability_service:5001"

# ====================
# REST Endpoint - Room Recommendation
# ====================
@app.route('/api/rooms', methods=['GET'])
def get_rooms():
    try:
        # Ambil semua data ruangan dari Room Availability Service
        response = requests.get(f"{ROOM_AVAILABILITY_SERVICE}/rooms")
        if response.status_code != 200:
            return jsonify({'error': 'Gagal mengambil data ruangan'}), 500

        rooms = response.json()
        return jsonify(rooms)

    # Error handling jika gagal request ke service availability
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Gagal komunikasi ke Room Availability Service: {str(e)}'}), 500

    # Error handling umum
    except Exception as e:
        return jsonify({'error': f'Kesalahan tidak terduga: {str(e)}'}), 500

@app.route('/api/rooms/recommend-rooms', methods=['GET'])
def recommend_rooms():
    # Ambil parameter dari query string
    kapasitas = request.args.get('kapasitas', type=int)
    lokasi = request.args.get('lokasi', '').lower()  # bisa kosong

    # Validasi parameter kapasitas wajib diisi
    if kapasitas is None:
        return jsonify({'error': 'Parameter "kapasitas" wajib diisi'}), 400

    try:
        # Ambil semua data ruangan dari Room Availability Service
        response = requests.get(f"{ROOM_AVAILABILITY_SERVICE}/rooms")
        if response.status_code != 200:
            return jsonify({'error': 'Gagal mengambil data ruangan'}), 500

        rooms = response.json()

        # Filter ruangan berdasarkan kapasitas dan (jika ada) lokasi
        suitable_rooms = []
        for room in rooms:
            if room['kapasitas'] >= kapasitas:
                if lokasi:
                    if lokasi in room.get('lokasi', '').lower():
                        suitable_rooms.append(room)
                else:
                    suitable_rooms.append(room)

        # Urutkan hasil berdasarkan selisih kapasitas terkecil
        suitable_rooms.sort(key=lambda x: abs(x['kapasitas'] - kapasitas))

        # Kembalikan hasil rekomendasi dalam format JSON
        return jsonify({
            'recommended_rooms': suitable_rooms,
            'total_recommendations': len(suitable_rooms)
        })

    # Error handling jika gagal request ke service availability
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Gagal komunikasi ke Room Availability Service: {str(e)}'}), 500

    # Error handling umum
    except Exception as e:
        return jsonify({'error': f'Kesalahan tidak terduga: {str(e)}'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

# ====================
# GraphQL
# ====================
class RoomType(ObjectType):
    room_id = Int(required=True)
    nama_ruangan = String(required=True)
    kapasitas = Int(required=True)
    fasilitas = String(required=True)
    lokasi = String(required=True)

class Query(ObjectType):
    rooms = graphene.List(RoomType)
    recommend_rooms = graphene.List(
        RoomType,
        kapasitas=graphene.Int(required=True),
        lokasi=graphene.String()
    )

    def resolve_rooms(self, info):
        try:
            response = requests.get(f"{ROOM_AVAILABILITY_SERVICE}/rooms")
            if response.status_code != 200:
                return []
            return response.json()
        except Exception as e:
            return []

    def resolve_recommend_rooms(self, info, kapasitas, lokasi=None):
        try:
            # Get all rooms from Room Availability Service
            response = requests.get(f"{ROOM_AVAILABILITY_SERVICE}/rooms")
            if response.status_code != 200:
                return []

            rooms = response.json()

            # Filter rooms based on capacity and optional location
            suitable_rooms = []
            for room in rooms:
                if room['kapasitas'] >= kapasitas:
                    if lokasi:
                        if lokasi.lower() in room.get('lokasi', '').lower():
                            suitable_rooms.append(room)
                    else:
                        suitable_rooms.append(room)

            # Sort results by smallest capacity difference
            suitable_rooms.sort(key=lambda x: abs(x['kapasitas'] - kapasitas))

            return suitable_rooms

        except Exception as e:
            return []

schema = graphene.Schema(query=Query)

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
# Run Application
# ====================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
