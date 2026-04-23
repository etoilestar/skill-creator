import uuid
from datetime import datetime, timezone
from app.extensions import db


class Skill(db.Model):
    __tablename__ = 'skills'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = db.Column(db.String(36), db.ForeignKey('skill_sessions.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    code = db.Column(db.Text, nullable=False)
    spec = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(50), default='draft')
    test_result = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    sandbox_runs = db.relationship('SandboxRun', backref='skill', lazy=True)

    def __repr__(self):
        return f'<Skill {self.name}>'
