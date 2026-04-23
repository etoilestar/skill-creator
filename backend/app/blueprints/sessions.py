from flask import Blueprint, request, current_app
from app.utils.response import success, error
from app.services.session_service import SessionService
from app.schemas.session import SessionSchema

sessions_bp = Blueprint('sessions', __name__, url_prefix='/api/sessions')

_schema = SessionSchema()


@sessions_bp.route('/', methods=['POST'])
def create_session():
    json_data = request.get_json()
    if not json_data or 'model_config_id' not in json_data:
        return error('model_config_id is required', 400)
    session = SessionService.create_session(json_data['model_config_id'])
    if not session:
        return error('Model config not found or inactive', 404)
    return success(_schema.dump(session), 201)


@sessions_bp.route('/<string:session_id>', methods=['GET'])
def get_session(session_id):
    session = SessionService.get_session(session_id)
    if not session:
        return error('Session not found', 404)
    return success(_schema.dump(session))


@sessions_bp.route('/<string:session_id>/message', methods=['POST'])
def send_message(session_id):
    json_data = request.get_json()
    if not json_data or 'message' not in json_data:
        return error('message is required', 400)
    session = SessionService.get_session(session_id)
    if not session:
        return error('Session not found', 404)
    from app.tasks.skill_tasks import process_session_message
    task = process_session_message.delay(session_id, json_data['message'])
    return success({'task_id': task.id, 'session_id': session_id}, 202)


@sessions_bp.route('/<string:session_id>/confirm', methods=['POST'])
def confirm_session(session_id):
    session = SessionService.get_session(session_id)
    if not session:
        return error('Session not found', 404)
    if not session.current_spec:
        return error('No skill spec to confirm', 400)
    from app.tasks.skill_tasks import create_skill_from_session
    task = create_skill_from_session.delay(session_id)
    return success({'task_id': task.id, 'session_id': session_id}, 202)


@sessions_bp.route('/<string:session_id>', methods=['DELETE'])
def abandon_session(session_id):
    session = SessionService.abandon_session(session_id)
    if not session:
        return error('Session not found', 404)
    return success({'message': 'Session abandoned'})
