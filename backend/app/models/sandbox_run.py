import uuid
from datetime import datetime, timezone
from app.extensions import db


class SandboxRun(db.Model):
    __tablename__ = 'sandbox_runs'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    skill_id = db.Column(db.String(36), db.ForeignKey('skills.id'), nullable=False)
    container_id = db.Column(db.String(255), nullable=True)
    input_data = db.Column(db.JSON, nullable=False)
    output_data = db.Column(db.JSON, nullable=True)
    stdout = db.Column(db.Text, nullable=True)
    stderr = db.Column(db.Text, nullable=True)
    exit_code = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(50), default='pending')
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<SandboxRun {self.id}>'
