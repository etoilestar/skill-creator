import uuid
from datetime import datetime
from app.extensions import db


class ModelConfig(db.Model):
    __tablename__ = 'model_configs'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), unique=True, nullable=False)
    provider = db.Column(db.String(100), nullable=False)
    model_id = db.Column(db.String(255), nullable=False)
    api_base = db.Column(db.String(500), nullable=True)
    api_key_env = db.Column(db.String(255), nullable=False)
    max_tokens = db.Column(db.Integer, default=4096)
    temperature = db.Column(db.Float, default=0.7)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sessions = db.relationship('SkillSession', backref='model_config', lazy=True)

    def __repr__(self):
        return f'<ModelConfig {self.name}>'
