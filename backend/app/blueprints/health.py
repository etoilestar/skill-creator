from datetime import datetime, timezone
from flask import Blueprint
from app.utils.response import success

health_bp = Blueprint('health', __name__, url_prefix='/api/health')


@health_bp.route('/', methods=['GET'])
def health_check():
    return success({
        'status': 'ok',
        'timestamp': datetime.now(timezone.utc).isoformat(),
    })
