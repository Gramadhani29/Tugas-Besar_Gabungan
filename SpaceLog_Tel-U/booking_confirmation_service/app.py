# =====================
# Import Libraries
# =====================
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, date
import logging
import requests
from enum import Enum
import graphene
from graphene import ObjectType, String, Int, Field, Mutation, Boolean, List
import pytz

# ====================
# App Initialization
# ====================
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ====================
# Service Endpoint Config
# ====================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///booking_confirmation.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

ROOM_BOOKING_SERVICE = "http://room_booking_service:5003"

# ====================
# Database Initialization
# ====================
db = SQLAlchemy(app)

# ====================
# Logging Configuration
# ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ====================
# Booking Status Enum
# ====================
class BookingStatus(str, Enum):
    PENDING = 'Pending'
    APPROVED = 'Approved'
    REJECTED = 'Rejected'

# ====================
# Approval Log Model
# ====================
class ApprovalLog(db.Model):
    approval_id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, nullable=False)
    tanggal_approval = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(255), nullable=False)
    keterangan_reject = db.Column(db.String(255))

# ====================
# Create DB
# ====================
with app.app_context():
    db.create_all()

# ====================
# Routes
# ====================
@app.route('/api/approval-status/<int:booking_id>', methods=['GET'])
def get_approval_status(booking_id):
    approval = ApprovalLog.query.filter_by(booking_id=booking_id).order_by(ApprovalLog.tanggal_approval.desc()).first()
    if not approval:
        return jsonify({'status': 'Pending', 'keterangan_reject': None}), 200
    return jsonify({
        'status': approval.status,
        'keterangan_reject': approval.keterangan_reject
    }), 200

@app.route('/api/update-booking-status/<int:booking_id>', methods=['POST'])
def update_booking_status(booking_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        new_status = data.get('status')
        keterangan_reject = data.get('keterangan_reject')

        if not new_status:
            return jsonify({'error': 'Status is required'}), 400

        if new_status not in [BookingStatus.APPROVED.value, BookingStatus.REJECTED.value, BookingStatus.PENDING.value]:
            return jsonify({'error': 'Invalid status value'}), 400

        if new_status == BookingStatus.REJECTED.value and not keterangan_reject:
            return jsonify({'error': 'Keterangan reject wajib diisi jika status Rejected'}), 400

        # Get booking from room_booking_service
        booking_response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings/{booking_id}")
        if booking_response.status_code != 200:
            return jsonify({'error': 'Booking not found in room_booking_service'}), 404

        booking_data = booking_response.json()

        # Get or create approval log
        approval_log = ApprovalLog.query.filter_by(booking_id=booking_id).first()
        if not approval_log:
            approval_log = ApprovalLog(
                booking_id=booking_id,
                tanggal_approval=datetime.now(pytz.timezone('Asia/Jakarta')),
                status=new_status,
                keterangan_reject=keterangan_reject if new_status == BookingStatus.REJECTED.value else None
            )
            db.session.add(approval_log)
        else:
            if approval_log.status != 'Pending':
                return jsonify({'error': 'Booking status already finalized'}), 400
            approval_log.tanggal_approval = datetime.now(pytz.timezone('Asia/Jakarta'))
            approval_log.status = new_status
            approval_log.keterangan_reject = keterangan_reject if new_status == BookingStatus.REJECTED.value else None

        db.session.commit()

        # Sync with room_booking_service
        try:
            sync_response = requests.post(
                f"{ROOM_BOOKING_SERVICE}/api/update-booking-status/{booking_id}",
                json={
                    'status_booking': approval_log.status,
                    'keterangan_reject': approval_log.keterangan_reject,
                    'approval_id': approval_log.approval_id
                },
                timeout=2
            )
            if sync_response.status_code != 200:
                print(f"Failed to sync with room_booking_service: {sync_response.text}")
                return jsonify({'error': 'Failed to sync with room booking service'}), 500
        except Exception as e:
            print(f"Error syncing with room_booking_service: {e}")
            return jsonify({'error': 'Failed to sync with room booking service'}), 500

        return jsonify({
            'success': True,
            'message': 'Booking status updated successfully',
            'approval_log': {
                'approval_id': approval_log.approval_id,
                'booking_id': approval_log.booking_id,
                'status': approval_log.status,
                'keterangan_reject': approval_log.keterangan_reject,
                'tanggal_approval': approval_log.tanggal_approval.strftime('%Y-%m-%d %H:%M:%S')
            },
            'booking': booking_data
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/sync-booking', methods=['POST'])
def sync_booking():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Create approval log first
        approval_log = ApprovalLog(
            booking_id=data['booking_id'],
            tanggal_approval=datetime.now(pytz.timezone('Asia/Jakarta')),
            status='Pending',
            keterangan_reject=None
        )
        db.session.add(approval_log)
        db.session.commit()

        # Create new booking in booking_confirmation.db
        booking = Booking(
            booking_id=data['booking_id'],
            event_id=data['event_id'],
            room_id=data['room_id'],
            tanggal_booking=datetime.strptime(data['tanggal_booking'], '%Y-%m-%d %H:%M:%S'),
            tanggal_mulai=datetime.strptime(data['tanggal_mulai'], '%Y-%m-%d').date(),
            tanggal_selesai=datetime.strptime(data['tanggal_selesai'], '%Y-%m-%d').date(),
            status_booking=approval_log.status,  # Use status from ApprovalLog
            keterangan_reject=None,
        )
        db.session.add(booking)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Booking synchronized successfully',
            'booking': {
                'booking_id': booking.booking_id,
                'event_id': booking.event_id,
                'room_id': booking.room_id,
                'tanggal_booking': booking.tanggal_booking.strftime('%Y-%m-%d %H:%M:%S'),
                'tanggal_mulai': booking.tanggal_mulai.strftime('%Y-%m-%d'),
                'tanggal_selesai': booking.tanggal_selesai.strftime('%Y-%m-%d'),
                'status_booking': booking.status_booking,
                'keterangan_reject': booking.keterangan_reject
            },
            'approval_log': {
                'approval_id': approval_log.approval_id,
                'booking_id': approval_log.booking_id,
                'status': approval_log.status,
                'keterangan_reject': approval_log.keterangan_reject,
                'tanggal_approval': approval_log.tanggal_approval.strftime('%Y-%m-%d %H:%M:%S')
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

@app.route('/api/bookings/<int:booking_id>', methods=['GET'])
def get_booking(booking_id):
    try:
        # Get booking from room_booking_service
        response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings/{booking_id}")
        if response.status_code != 200:
            return jsonify({'error': 'Booking not found in room_booking_service'}), 404

        booking_data = response.json()
        
        # Get approval status from local database
        approval = ApprovalLog.query.filter_by(booking_id=booking_id).order_by(ApprovalLog.tanggal_approval.desc()).first()
        
        # Combine booking data with approval status
        result = {
            **booking_data,
            'approval_status': {
                'status': approval.status if approval else 'Pending',
                'keterangan_reject': approval.keterangan_reject if approval else None,
                'tanggal_approval': approval.tanggal_approval.strftime('%Y-%m-%d %H:%M:%S') if approval else None,
                'approval_id': approval.approval_id if approval else None
            }
        }
        
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting booking: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bookings', methods=['GET'])
def get_all_bookings():
    try:
        # Get all bookings from room_booking_service
        response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings")
        if response.status_code != 200:
            return jsonify({'error': 'Failed to get bookings from room_booking_service'}), 500

        bookings = response.json()
        results = []

        for booking in bookings:
            booking_id = booking['booking_id']
            # Get approval status for each booking
            approval = ApprovalLog.query.filter_by(booking_id=booking_id).order_by(ApprovalLog.tanggal_approval.desc()).first()
            
            # Combine booking data with approval status
            result = {
                **booking,
                'approval_status': {
                    'status': approval.status if approval else 'Pending',
                    'keterangan_reject': approval.keterangan_reject if approval else None,
                    'tanggal_approval': approval.tanggal_approval.strftime('%Y-%m-%d %H:%M:%S') if approval else None,
                    'approval_id': approval.approval_id if approval else None
                }
            }
            results.append(result)

        return jsonify(results), 200

    except Exception as e:
        logger.error(f"Error getting all bookings: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ====================
# GraphQL Types
# ====================
class ApprovalStatusType(graphene.ObjectType):
    status = graphene.String()
    keteranganReject = graphene.String()
    tanggalApproval = graphene.String()
    approvalId = graphene.Int()

    def resolve_tanggalApproval(self, info):
        if hasattr(self, 'tanggal_approval'):
            if isinstance(self.tanggal_approval, datetime):
                jakarta_tz = pytz.timezone('Asia/Jakarta')
                local_dt = self.tanggal_approval.astimezone(jakarta_tz)
                return local_dt.strftime('%Y-%m-%d %H:%M:%S')
            return self.tanggal_approval
        return None

class BookingType(graphene.ObjectType):
    bookingId = graphene.Int()
    eventId = graphene.Int()
    roomId = graphene.Int()
    tanggalBooking = graphene.String()
    tanggalMulai = graphene.String()
    tanggalSelesai = graphene.String()
    statusBooking = graphene.String()
    keteranganReject = graphene.String()
    approvalStatus = graphene.Field(ApprovalStatusType)

    def resolve_tanggalBooking(self, info):
        if hasattr(self, 'tanggal_booking'):
            if isinstance(self.tanggal_booking, datetime):
                jakarta_tz = pytz.timezone('Asia/Jakarta')
                local_dt = self.tanggal_booking.astimezone(jakarta_tz)
                return local_dt.strftime('%Y-%m-%d %H:%M:%S')
            return self.tanggal_booking
        return None

    def resolve_tanggalMulai(self, info):
        if hasattr(self, 'tanggal_mulai'):
            if isinstance(self.tanggal_mulai, datetime):
                jakarta_tz = pytz.timezone('Asia/Jakarta')
                local_dt = self.tanggal_mulai.astimezone(jakarta_tz)
                return local_dt.strftime('%Y-%m-%d %H:%M:%S')
            return self.tanggal_mulai
        return None

    def resolve_tanggalSelesai(self, info):
        if hasattr(self, 'tanggal_selesai'):
            if isinstance(self.tanggal_selesai, datetime):
                jakarta_tz = pytz.timezone('Asia/Jakarta')
                local_dt = self.tanggal_selesai.astimezone(jakarta_tz)
                return local_dt.strftime('%Y-%m-%d %H:%M:%S')
            return self.tanggal_selesai
        return None

class ApprovalLogType(graphene.ObjectType):
    approvalId = graphene.Int()
    bookingId = graphene.Int()
    tanggalApproval = graphene.String()
    status = graphene.String()
    keteranganReject = graphene.String()

    def resolve_tanggalApproval(self, info):
        if hasattr(self, 'tanggal_approval'):
            if isinstance(self.tanggal_approval, datetime):
                jakarta_tz = pytz.timezone('Asia/Jakarta')
                local_dt = self.tanggal_approval.astimezone(jakarta_tz)
                return local_dt.strftime('%Y-%m-%d %H:%M:%S')
            return self.tanggal_approval
        return None

# ====================
# GraphQL Mutations
# ====================
class UpdateBookingStatus(Mutation):
    class Arguments:
        booking_id = Int(required=True)
        status = String(required=True)
        keterangan_reject = String()

    success = Boolean()
    message = String()
    booking = Field(BookingType)
    approval_log = Field(ApprovalLogType)

    def mutate(self, info, booking_id, status, keterangan_reject=None):
        try:
            # Validate status
            if status not in ['Pending', 'Approved', 'Rejected']:
                return UpdateBookingStatus(
                    success=False,
                    message="Invalid status. Must be one of: Pending, Approved, Rejected"
                )

            # Validate keterangan_reject for Rejected status
            if status == 'Rejected' and not keterangan_reject:
                return UpdateBookingStatus(
                    success=False,
                    message="Rejection reason is required when status is Rejected"
                )

            # Get booking from room_booking_service
            try:
                booking_response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings/{booking_id}")
                if booking_response.status_code != 200:
                    return UpdateBookingStatus(success=False, message="Booking not found in room_booking_service")
                booking_data = booking_response.json()
            except Exception as e:
                return UpdateBookingStatus(success=False, message=f"Failed to get booking: {str(e)}")

            # Get or create approval log
            approval_log = ApprovalLog.query.filter_by(booking_id=booking_id).first()
            if not approval_log:
                approval_log = ApprovalLog(booking_id=booking_id)

            # Update approval log with Jakarta timezone
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            approval_log.status = status
            approval_log.keterangan_reject = keterangan_reject
            approval_log.tanggal_approval = datetime.now(jakarta_tz)

            # Sync with room_booking_service
            try:
                sync_data = {
                    'status_booking': status,
                    'keterangan_reject': keterangan_reject,
                    'approval_id': approval_log.approval_id
                }
                sync_response = requests.post(
                    f"{ROOM_BOOKING_SERVICE}/api/update-booking-status/{booking_id}",
                    json=sync_data
                )
                if sync_response.status_code != 200:
                    return UpdateBookingStatus(
                        success=False,
                        message=f"Failed to sync with room_booking_service: {sync_response.text}"
                    )
            except Exception as e:
                return UpdateBookingStatus(success=False, message=f"Failed to sync with room_booking_service: {str(e)}")

            # Save changes
            db.session.add(approval_log)
            db.session.commit()

            # Get updated booking data
            try:
                updated_booking_response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings/{booking_id}")
                if updated_booking_response.status_code == 200:
                    updated_booking_data = updated_booking_response.json()
                else:
                    updated_booking_data = booking_data
            except Exception:
                updated_booking_data = booking_data

            # Create ApprovalStatusType instance
            approval_status = ApprovalStatusType()
            approval_status.status = approval_log.status
            approval_status.keteranganReject = approval_log.keterangan_reject
            approval_status.tanggal_approval = approval_log.tanggal_approval
            approval_status.approvalId = approval_log.approval_id

            # Create BookingType instance from JSON data
            booking_type = BookingType()
            booking_type.bookingId = updated_booking_data.get('booking_id')
            booking_type.eventId = updated_booking_data.get('event_id')
            booking_type.roomId = updated_booking_data.get('room_id')
            booking_type.tanggal_booking = updated_booking_data.get('tanggal_booking')
            booking_type.tanggal_mulai = updated_booking_data.get('tanggal_mulai')
            booking_type.tanggal_selesai = updated_booking_data.get('tanggal_selesai')
            booking_type.statusBooking = status
            booking_type.keteranganReject = updated_booking_data.get('keterangan_reject')
            booking_type.approvalStatus = approval_status

            # Create ApprovalLogType instance
            approval_log_type = ApprovalLogType()
            approval_log_type.approvalId = approval_log.approval_id
            approval_log_type.bookingId = approval_log.booking_id
            approval_log_type.status = approval_log.status
            approval_log_type.keteranganReject = approval_log.keterangan_reject
            approval_log_type.tanggal_approval = approval_log.tanggal_approval

            return UpdateBookingStatus(
                success=True,
                message="Booking status updated successfully",
                booking=booking_type,
                approval_log=approval_log_type
            )

        except Exception as e:
            db.session.rollback()
            return UpdateBookingStatus(success=False, message=str(e))

class DeleteBooking(Mutation):
    class Arguments:
        bookingId = Int(required=True)

    success = Boolean()
    message = String()

    def mutate(self, info, bookingId):
        try:
            # Delete approval log first
            approval_log = ApprovalLog.query.filter_by(booking_id=bookingId).first()
            if approval_log:
                db.session.delete(approval_log)
                db.session.commit()

            # Delete booking from room_booking_service
            response = requests.delete(f"{ROOM_BOOKING_SERVICE}/api/bookings/{bookingId}")
            
            if response.status_code == 200:
                return DeleteBooking(
                    success=True,
                    message="Booking deleted successfully"
                )
            else:
                error_message = response.json().get('error', 'Unknown error')
                return DeleteBooking(
                    success=False,
                    message=f"Failed to delete booking in room_booking_service: {error_message}"
                )
        except Exception as e:
            db.session.rollback()
            return DeleteBooking(
                success=False,
                message=f"Error deleting booking: {str(e)}"
            )

class Mutation(ObjectType):
    update_booking_status = UpdateBookingStatus.Field()
    delete_booking = DeleteBooking.Field()

# ====================
# GraphQL Queries
# ====================
class Query(ObjectType):
    booking = Field(BookingType, bookingId=Int(required=True))
    bookings = List(BookingType)
    approval_log = Field(ApprovalLogType, bookingId=Int(required=True))
    approval_logs = List(ApprovalLogType)

    def resolve_booking(self, info, bookingId):
        try:
            # Get booking from room_booking_service
            booking_response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings/{bookingId}")
            if booking_response.status_code != 200:
                return None
            
            booking_data = booking_response.json()
            
            # Get approval status
            approval_log = ApprovalLog.query.filter_by(booking_id=bookingId).first()
            
            # Create ApprovalStatusType instance
            approval_status = ApprovalStatusType()
            if approval_log:
                approval_status.status = approval_log.status
                approval_status.keteranganReject = approval_log.keterangan_reject
                approval_status.tanggal_approval = approval_log.tanggal_approval
                approval_status.approvalId = approval_log.approval_id

            # Create BookingType instance
            booking_type = BookingType()
            booking_type.bookingId = bookingId
            booking_type.eventId = booking_data.get('event_id')
            booking_type.roomId = booking_data.get('room_id')
            booking_type.tanggal_booking = booking_data.get('tanggal_booking')
            booking_type.tanggal_mulai = booking_data.get('tanggal_mulai')
            booking_type.tanggal_selesai = booking_data.get('tanggal_selesai')
            booking_type.statusBooking = approval_status.status if approval_log else None
            booking_type.keteranganReject = approval_status.keteranganReject if approval_log else None
            booking_type.approvalStatus = approval_status if approval_log else None

            return booking_type
        except Exception as e:
            print(f"Error in resolve_booking: {str(e)}")
            return None

    def resolve_bookings(self, info):
        try:
            # Get all bookings from room_booking_service
            booking_response = requests.get(f"{ROOM_BOOKING_SERVICE}/api/bookings")
            if booking_response.status_code != 200:
                return []
            
            bookings_data = booking_response.json()
            result = []

            for booking_data in bookings_data:
                booking_id = booking_data.get('booking_id')
                if not booking_id:
                    continue

                # Get approval status for each booking
                approval_log = ApprovalLog.query.filter_by(booking_id=booking_id).first()
                
                # Create ApprovalStatusType instance
                approval_status = ApprovalStatusType()
                if approval_log:
                    approval_status.status = approval_log.status
                    approval_status.keteranganReject = approval_log.keterangan_reject
                    approval_status.tanggal_approval = approval_log.tanggal_approval
                    approval_status.approvalId = approval_log.approval_id

                # Create BookingType instance
                booking_type = BookingType()
                booking_type.bookingId = booking_id
                booking_type.eventId = booking_data.get('event_id')
                booking_type.roomId = booking_data.get('room_id')
                booking_type.tanggal_booking = booking_data.get('tanggal_booking')
                booking_type.tanggal_mulai = booking_data.get('tanggal_mulai')
                booking_type.tanggal_selesai = booking_data.get('tanggal_selesai')
                booking_type.statusBooking = approval_status.status if approval_log else None
                booking_type.keteranganReject = approval_status.keteranganReject if approval_log else None
                booking_type.approvalStatus = approval_status if approval_log else None

                result.append(booking_type)

            return result
        except Exception as e:
            print(f"Error in resolve_bookings: {str(e)}")
            return []

    def resolve_approval_log(self, info, bookingId):
        try:
            approval_log = ApprovalLog.query.filter_by(booking_id=bookingId).first()
            if not approval_log:
                return None

            approval_log_type = ApprovalLogType()
            approval_log_type.approvalId = approval_log.approval_id
            approval_log_type.bookingId = approval_log.booking_id
            approval_log_type.status = approval_log.status
            approval_log_type.keteranganReject = approval_log.keterangan_reject
            approval_log_type.tanggal_approval = approval_log.tanggal_approval

            return approval_log_type
        except Exception as e:
            print(f"Error in resolve_approval_log: {str(e)}")
            return None

    def resolve_approval_logs(self, info):
        try:
            approval_logs = ApprovalLog.query.all()
            result = []

            for approval_log in approval_logs:
                approval_log_type = ApprovalLogType()
                approval_log_type.approvalId = approval_log.approval_id
                approval_log_type.bookingId = approval_log.booking_id
                approval_log_type.status = approval_log.status
                approval_log_type.keteranganReject = approval_log.keterangan_reject
                approval_log_type.tanggal_approval = approval_log.tanggal_approval

                result.append(approval_log_type)

            return result
        except Exception as e:
            print(f"Error in resolve_approval_logs: {str(e)}")
            return []

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
    app.run(host='0.0.0.0', port=5006)