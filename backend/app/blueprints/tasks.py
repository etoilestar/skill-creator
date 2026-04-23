from flask import Blueprint
from app.utils.response import success, error
from app.tasks.celery_app import celery_app

tasks_bp = Blueprint('tasks', __name__, url_prefix='/api/tasks')


@tasks_bp.route('/<string:task_id>', methods=['GET'])
def get_task_status(task_id):
    task_result = celery_app.AsyncResult(task_id)
    data = {
        'task_id': task_id,
        'status': task_result.status,
        'result': None,
        'error': None,
    }
    if task_result.successful():
        data['result'] = task_result.result
    elif task_result.failed():
        data['error'] = str(task_result.result)
    return success(data)
