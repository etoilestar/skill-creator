import uuid
from datetime import datetime
from app.extensions import db
from app.models.sandbox_run import SandboxRun
from app.models.skill import Skill


class SandboxService:
    CONTAINER_IMAGE = 'python:3.11-slim'
    TIMEOUT_SECONDS = 30

    @staticmethod
    def run_skill(skill_id, input_data):
        skill = Skill.query.filter_by(id=skill_id).first()
        if not skill:
            return None
        sandbox_run = SandboxRun(
            skill_id=skill_id,
            input_data=input_data,
            status='pending',
        )
        db.session.add(sandbox_run)
        db.session.commit()
        return sandbox_run

    @staticmethod
    def execute_in_docker(sandbox_run_id):
        sandbox_run = SandboxRun.query.filter_by(id=sandbox_run_id).first()
        if not sandbox_run:
            return None

        skill = Skill.query.filter_by(id=sandbox_run.skill_id).first()
        if not skill:
            sandbox_run.status = 'failed'
            sandbox_run.stderr = 'Skill not found'
            db.session.commit()
            return sandbox_run

        sandbox_run.status = 'running'
        sandbox_run.started_at = datetime.utcnow()
        db.session.commit()

        try:
            import docker
            import json as _json
            client = docker.from_env()
            code = skill.code
            input_json = _json.dumps(sandbox_run.input_data)
            script = f"""
import json
import sys

input_data = json.loads({repr(input_json)})

{code}
"""
            container = client.containers.run(
                SandboxService.CONTAINER_IMAGE,
                command=['python', '-c', script],
                remove=True,
                detach=False,
                stdout=True,
                stderr=True,
                timeout=SandboxService.TIMEOUT_SECONDS,
            )
            sandbox_run.stdout = container.decode('utf-8') if isinstance(container, bytes) else str(container)
            sandbox_run.exit_code = 0
            sandbox_run.status = 'success'
        except Exception as exc:
            sandbox_run.status = 'failed'
            sandbox_run.stderr = str(exc)
            sandbox_run.exit_code = 1
        finally:
            sandbox_run.finished_at = datetime.utcnow()
            db.session.commit()

        return sandbox_run

    @staticmethod
    def get_run(sandbox_run_id):
        return SandboxRun.query.filter_by(id=sandbox_run_id).first()
