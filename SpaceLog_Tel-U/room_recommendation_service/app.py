# ====================
# Import Libraries
# ====================
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

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
# Run Application
# ====================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
