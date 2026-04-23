import uuid
from datetime import datetime, timezone
from app.extensions import db


class SkillSession(db.Model):
    __tablename__ = 'skill_sessions'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    model_config_id = db.Column(db.String(36), db.ForeignKey('model_configs.id'), nullable=False)
    user_id = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(50), default='active')
    context = db.Column(db.JSON, default=list)
    current_spec = db.Column(db.JSON, nullable=True)
    kernel_id = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    skills = db.relationship('Skill', backref='session', lazy=True)

    def __repr__(self):
        return f'<SkillSession {self.id}>'
