from datetime import datetime
from app.extensions import db
from app.models.session import SkillSession
from app.models.model_config import ModelConfig


class SessionService:
    @staticmethod
    def create_session(model_config_id):
        model_config = ModelConfig.query.filter_by(id=model_config_id, is_active=True).first()
        if not model_config:
            return None
        session = SkillSession(
            model_config_id=model_config_id,
            status='active',
            context=[],
            current_spec=None,
        )
        db.session.add(session)
        db.session.commit()
        return session

    @staticmethod
    def get_session(session_id):
        return SkillSession.query.filter_by(id=session_id).first()

    @staticmethod
    def append_message(session_id, role, content):
        session = SkillSession.query.filter_by(id=session_id).first()
        if not session:
            return None
        context = list(session.context or [])
        context.append({'role': role, 'content': content, 'timestamp': datetime.utcnow().isoformat()})
        session.context = context
        db.session.commit()
        return session

    @staticmethod
    def update_spec(session_id, spec_dict):
        session = SkillSession.query.filter_by(id=session_id).first()
        if not session:
            return None
        session.current_spec = spec_dict
        db.session.commit()
        return session

    @staticmethod
    def abandon_session(session_id):
        session = SkillSession.query.filter_by(id=session_id).first()
        if not session:
            return None
        session.status = 'abandoned'
        db.session.commit()
        return session

    @staticmethod
    def complete_session(session_id):
        session = SkillSession.query.filter_by(id=session_id).first()
        if not session:
            return None
        session.status = 'completed'
        db.session.commit()
        return session
