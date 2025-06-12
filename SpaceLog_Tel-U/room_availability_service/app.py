# ====================
# Import Libraries
# ====================
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import graphene
from graphene import ObjectType, String, Int, Field, Mutation

# ====================
# App Initialization
# ====================
app = Flask(__name__)
CORS(app) # Mengaktifkan CORS agar bisa diakses dari frontend/backend lain

# ====================
# Service Endpoint Config
# ====================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///room_availability.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ====================
# Database Initialization
# ====================
db = SQLAlchemy(app)

# ====================
# Model
# ====================
class Room(db.Model):
    room_id = db.Column(db.Integer, primary_key=True)
    nama_ruangan = db.Column(db.String(255), nullable=False)
    kapasitas = db.Column(db.Integer, nullable=False)
    fasilitas = db.Column(db.String(1000))
    lokasi = db.Column(db.String(255))

# ====================
# Create DB
# ====================
with app.app_context():
    db.create_all()

# ====================
# REST Endpoints
# ====================


@app.route('/rooms', methods=['GET'])
def get_rooms():
    rooms = Room.query.all()
    return jsonify([{
        'room_id': room.room_id,
        'nama_ruangan': room.nama_ruangan,
        'kapasitas': room.kapasitas,
        'fasilitas': room.fasilitas,
        'lokasi': room.lokasi
    } for room in rooms])

@app.route('/rooms/<int:room_id>', methods=['GET'])
def get_room_detail(room_id):
    room = Room.query.get_or_404(room_id)
    return jsonify({
        'room_id': room.room_id,
        'nama_ruangan': room.nama_ruangan,
        'kapasitas': room.kapasitas,
        'fasilitas': room.fasilitas,
        'lokasi': room.lokasi
    })

@app.route('/locations', methods=['GET'])
def get_locations():
    locations = db.session.query(Room.lokasi).distinct().all()
    return jsonify([loc[0] for loc in locations if loc[0]])

@app.route('/check-availability', methods=['GET'])
def check_availability():
    try:
        room_id = request.args.get('room_id', type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if not all([room_id, start_date, end_date]):
            return jsonify({'error': 'Missing required parameters'}), 400

        # For now, we'll just check if the room exists
        # In a real implementation, you would check against a schedule/booking database
        room = Room.query.get(room_id)
        if not room:
            return jsonify({'error': 'Room not found'}), 404

        # Mock response - in a real implementation, you would check actual availability
        return jsonify({
            'is_available': True,
            'room_id': room_id,
            'start_date': start_date,
            'end_date': end_date
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

# ====================
# GraphQL
# ====================
class RoomType(ObjectType):
    room_id = Int()
    nama_ruangan = String()
    kapasitas = Int()
    fasilitas = String()
    lokasi = String()

# ----- CREATE -----
class CreateRoom(Mutation):
    class Arguments:
        nama_ruangan = String(required=True)
        kapasitas = Int(required=True)
        fasilitas = String()
        lokasi = String()

    room = Field(lambda: RoomType)

    def mutate(self, info, nama_ruangan, kapasitas, fasilitas=None, lokasi=None):
        room = Room(
            nama_ruangan=nama_ruangan,
            kapasitas=kapasitas,
            fasilitas=fasilitas,
            lokasi=lokasi
        )
        db.session.add(room)
        db.session.commit()
        return CreateRoom(room=room)

# ----- UPDATE -----
class UpdateRoom(Mutation):
    class Arguments:
        room_id = Int(required=True)
        nama_ruangan = String()
        kapasitas = Int()
        fasilitas = String()
        lokasi = String()

    room = Field(lambda: RoomType)

    def mutate(self, info, room_id, nama_ruangan=None, kapasitas=None, fasilitas=None, lokasi=None):
        room = Room.query.get(room_id)
        if not room:
            raise Exception("Room not found")

        if nama_ruangan is not None:
            room.nama_ruangan = nama_ruangan
        if kapasitas is not None:
            room.kapasitas = kapasitas
        if fasilitas is not None:
            room.fasilitas = fasilitas
        if lokasi is not None:
            room.lokasi = lokasi

        db.session.commit()
        return UpdateRoom(room=room)

# ----- DELETE -----
class DeleteRoom(Mutation):
    class Arguments:
        room_id = Int(required=True)

    ok = String()

    def mutate(self, info, room_id):
        room = Room.query.get(room_id)
        if not room:
            raise Exception("Room not found")
        db.session.delete(room)
        db.session.commit()
        return DeleteRoom(ok=f"Room ID {room_id} deleted")

# GraphQL schema
class Query(ObjectType):
    rooms = graphene.List(RoomType)

    def resolve_rooms(self, info):
        return Room.query.all()

class Mutation(ObjectType):
    create_room = CreateRoom.Field()
    update_room = UpdateRoom.Field()
    delete_room = DeleteRoom.Field()

schema = graphene.Schema(query=Query, mutation=Mutation)

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
    app.run(host='0.0.0.0', port=5001)
