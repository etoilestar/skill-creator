import json
from app.tasks.celery_app import celery_app


@celery_app.task(bind=True, name='skill_tasks.process_session_message')
def process_session_message(self, session_id, message):
    from app import create_app
    app = create_app()
    with app.app_context():
        from app.services.session_service import SessionService
        from app.kernel.skill_creator_adapter import SkillCreatorAdapter

        session = SessionService.get_session(session_id)
        if not session:
            return {'error': 'Session not found'}

        SessionService.append_message(session_id, 'user', message)

        adapter = SkillCreatorAdapter()
        response = adapter.send_message(session, message, session.kernel_id)

        SessionService.append_message(session_id, response['role'], response['content'])

        if 'spec' in response:
            SessionService.update_spec(session_id, response['spec'])

        updated_session = SessionService.get_session(session_id)
        return {
            'session_id': session_id,
            'status': updated_session.status,
            'current_spec': updated_session.current_spec,
        }


@celery_app.task(bind=True, name='skill_tasks.create_skill_from_session')
def create_skill_from_session(self, session_id):
    from app import create_app
    app = create_app()
    with app.app_context():
        from app.services.skill_service import SkillService
        from app.services.session_service import SessionService

        skill = SkillService.create_from_session(session_id)
        if not skill:
            return {'error': 'Could not create skill from session'}

        SessionService.complete_session(session_id)

        return {'skill_id': str(skill.id), 'status': 'created'}


@celery_app.task(bind=True, name='skill_tasks.run_sandbox_test')
def run_sandbox_test(self, sandbox_run_id):
    from app import create_app
    app = create_app()
    with app.app_context():
        from app.services.sandbox_service import SandboxService

        sandbox_run = SandboxService.execute_in_docker(sandbox_run_id)
        if not sandbox_run:
            return {'error': 'Sandbox run not found'}

        return {
            'sandbox_run_id': sandbox_run_id,
            'status': sandbox_run.status,
            'exit_code': sandbox_run.exit_code,
        }
