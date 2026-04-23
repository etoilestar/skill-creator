from flask import Blueprint, request
from app.utils.response import success, error
from app.services.sandbox_service import SandboxService
from app.schemas.sandbox_test import SandboxRunSchema

sandboxes_bp = Blueprint('sandboxes', __name__, url_prefix='/api/sandboxes')

_schema = SandboxRunSchema()


@sandboxes_bp.route('/run', methods=['POST'])
def run_sandbox():
    json_data = request.get_json()
    if not json_data:
        return error('Request body is required', 400)
    skill_id = json_data.get('skill_id')
    input_data = json_data.get('input_data', {})
    if not skill_id:
        return error('skill_id is required', 400)
    sandbox_run = SandboxService.run_skill(skill_id, input_data)
    if not sandbox_run:
        return error('Skill not found', 404)
    from app.tasks.skill_tasks import run_sandbox_test
    run_sandbox_test.delay(str(sandbox_run.id))
    return success(_schema.dump(sandbox_run), 202)


@sandboxes_bp.route('/<string:sandbox_run_id>', methods=['GET'])
def get_sandbox_run(sandbox_run_id):
    sandbox_run = SandboxService.get_run(sandbox_run_id)
    if not sandbox_run:
        return error('Sandbox run not found', 404)
    return success(_schema.dump(sandbox_run))
