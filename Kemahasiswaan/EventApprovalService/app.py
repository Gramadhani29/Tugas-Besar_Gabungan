from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import requests

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///event_approval.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Service URLs
ADD_EVENT_SERVICE = os.getenv('ADD_EVENT_SERVICE_URL', 'http://add_event_service:5008')

class EventApprovalLog(db.Model):
    approval_id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, nullable=False)
    tanggal_approval = db.Column(db.DateTime, nullable=False, default=datetime.now)
    status = db.Column(db.String(255), nullable=False)
    catatan = db.Column(db.String(1000))

with app.app_context():
    db.create_all()

@app.route('/api/events/approve', methods=['POST'])
def approve_event():
    data = request.json
    event_id = data.get('event_id')
    status = data.get('status')
    rejection_reason = data.get('rejection_reason', '')
    
    if not event_id or not status:
        return jsonify({'error': 'event_id and status are required'}), 400
        
    if status not in ['Approved', 'Rejected', 'Pending']:
        return jsonify({'error': 'Status must be Approved, Rejected, or Pending'}), 400
    
    try:
        # Update status in add_event_service
        update_response = requests.post(
            f"{ADD_EVENT_SERVICE}/api/events/{event_id}/update-status",
            json={'status_approval': status}
        )
        if update_response.status_code != 200:
            return jsonify({'error': 'Failed to update event status'}), 500
            
        # Log the approval
        log = EventApprovalLog(
            event_id=event_id, 
            status=status, 
            catatan=rejection_reason
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'message': 'Event status updated and approval logged'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/events/<int:event_id>/approval-logs', methods=['GET'])
def get_approval_logs(event_id):
    logs = EventApprovalLog.query.filter_by(event_id=event_id).order_by(EventApprovalLog.tanggal_approval.desc()).all()
    return jsonify([
        {
            'approval_id': log.approval_id,
            'event_id': log.event_id,
            'tanggal_approval': log.tanggal_approval.strftime('%Y-%m-%d %H:%M:%S'),
            'status': log.status,
            'catatan': log.catatan
        } for log in logs
    ])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5010) 