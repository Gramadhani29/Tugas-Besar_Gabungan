from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import requests
import graphene
from graphene import ObjectType, String, Int, Field, List, DateTime
from graphene_sqlalchemy import SQLAlchemyObjectType

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

# GraphQL Types
class EventApprovalLogType(SQLAlchemyObjectType):
    class Meta:
        model = EventApprovalLog
        interfaces = (graphene.relay.Node,)

# GraphQL Mutations
class ApproveEvent(graphene.Mutation):
    class Arguments:
        event_id = Int(required=True)
        status = String(required=True)
        rejection_reason = String()

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, event_id, status, rejection_reason=None):
        if status not in ['Approved', 'Rejected', 'Pending']:
            return ApproveEvent(success=False, message='Status must be Approved, Rejected, or Pending')
        
        try:
            # Update status in add_event_service
            update_response = requests.post(
                f"{ADD_EVENT_SERVICE}/api/events/{event_id}/update-status",
                json={'status_approval': status}
            )
            if update_response.status_code != 200:
                return ApproveEvent(success=False, message='Failed to update event status')
                
            # Log the approval
            log = EventApprovalLog(
                event_id=event_id, 
                status=status, 
                catatan=rejection_reason
            )
            db.session.add(log)
            db.session.commit()
            
            return ApproveEvent(success=True, message='Event status updated and approval logged')
        except Exception as e:
            return ApproveEvent(success=False, message=str(e))

# GraphQL Queries
class Query(ObjectType):
    approval_logs = List(EventApprovalLogType, event_id=Int(required=True))

    def resolve_approval_logs(self, info, event_id):
        return EventApprovalLog.query.filter_by(event_id=event_id).order_by(EventApprovalLog.tanggal_approval.desc()).all()

class Mutation(ObjectType):
    approve_event = ApproveEvent.Field()

schema = graphene.Schema(query=Query, mutation=Mutation)

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

with app.app_context():
    db.create_all()

# Existing REST endpoints
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