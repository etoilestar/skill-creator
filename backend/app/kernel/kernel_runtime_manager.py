import uuid
from datetime import datetime


class KernelRuntimeManager:
    def __init__(self):
        self._kernels = {}

    def start_kernel(self):
        kernel_id = str(uuid.uuid4())
        self._kernels[kernel_id] = {
            'kernel_id': kernel_id,
            'status': 'idle',
            'started_at': datetime.utcnow().isoformat(),
            'last_activity': datetime.utcnow().isoformat(),
        }
        return kernel_id

    def stop_kernel(self, kernel_id):
        if kernel_id not in self._kernels:
            return False
        del self._kernels[kernel_id]
        return True

    def restart_kernel(self, kernel_id):
        if kernel_id not in self._kernels:
            return False
        self._kernels[kernel_id]['status'] = 'idle'
        self._kernels[kernel_id]['last_activity'] = datetime.utcnow().isoformat()
        return True

    def list_kernels(self):
        return list(self._kernels.values())

    def get_kernel(self, kernel_id):
        return self._kernels.get(kernel_id)
