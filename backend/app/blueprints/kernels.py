from flask import Blueprint, current_app
from app.utils.response import success, error

kernels_bp = Blueprint('kernels', __name__, url_prefix='/api/kernels')


def _get_kernel_manager():
    return current_app.extensions['kernel_manager']


@kernels_bp.route('/', methods=['GET'])
def list_kernels():
    km = _get_kernel_manager()
    return success(km.list_kernels())


@kernels_bp.route('/', methods=['POST'])
def start_kernel():
    km = _get_kernel_manager()
    kernel_id = km.start_kernel()
    return success({'kernel_id': kernel_id}, 201)


@kernels_bp.route('/<string:kernel_id>', methods=['DELETE'])
def stop_kernel(kernel_id):
    km = _get_kernel_manager()
    result = km.stop_kernel(kernel_id)
    if not result:
        return error('Kernel not found', 404)
    return success({'message': 'Kernel stopped'})


@kernels_bp.route('/<string:kernel_id>/restart', methods=['POST'])
def restart_kernel(kernel_id):
    km = _get_kernel_manager()
    result = km.restart_kernel(kernel_id)
    if not result:
        return error('Kernel not found', 404)
    return success({'kernel_id': kernel_id, 'status': 'restarted'})
