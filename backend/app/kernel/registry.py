"""
backend/app/kernel/registry.py

内核注册表（KernelRegistry）。

职责：
    - 维护系统中所有已注册和已加载的内核实例
    - 提供内核的注册、获取、重载接口
    - 采用单例模式确保全局只有一个注册表实例
    - 为未来多内核并存、版本切换提供统一的管理入口

使用方式：
    registry = KernelRegistry.get_instance()
    kernel = registry.get_kernel("skill-creator")
    guide = kernel.get_skill_creation_guide()

扩展方向：
    - 后续可支持从数据库动态加载内核配置
    - 支持 A/B 测试（同一 kernel_id 的两个版本并行）
    - 支持内核热更新（不重启服务替换内核版本）
"""

import threading
from typing import Dict, List, Optional

from ..exceptions import KernelNotFoundError, KernelNotLoadedError
from .base import KernelAdapter, KernelMeta
from .skill_creator_impl import SkillCreatorKernelImpl


class KernelRegistry:
    """
    内核注册表（单例模式）。

    维护 kernel_id → KernelAdapter 实例的映射关系。
    所有对内核的访问都应通过此注册表进行，不应直接实例化 KernelAdapter 子类。

    线程安全：使用 threading.Lock 保护注册表的读写操作，
    确保在多线程 Flask 环境中安全访问。

    Attributes:
        _instance: 类级别的单例实例
        _lock: 类级别的线程锁（用于保护单例创建）
        _kernels: kernel_id → KernelAdapter 实例的字典
        _instance_lock: 实例级别的线程锁（保护 _kernels 的读写）
    """

    _instance: Optional["KernelRegistry"] = None
    _lock = threading.Lock()

    def __init__(self):
        """私有构造函数，外部应使用 get_instance() 获取单例。"""
        self._kernels: Dict[str, KernelAdapter] = {}
        self._instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "KernelRegistry":
        """
        获取 KernelRegistry 单例实例。

        使用双重检查锁定（Double-Checked Locking）保证线程安全的单例初始化。

        Returns:
            KernelRegistry 单例实例。
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def load_kernel(self, kernel_id: str, kernel_path: str) -> KernelAdapter:
        """
        加载并注册一个内核。

        根据 kernel_id 选择对应的 KernelAdapter 实现类进行实例化，
        完成加载后注册到内部映射表中。

        当前支持的 kernel_id：
        - "skill-creator": 使用 SkillCreatorKernelImpl

        Args:
            kernel_id: 内核唯一标识符
            kernel_path: 内核目录的绝对路径

        Returns:
            加载后的 KernelAdapter 实例。

        Raises:
            KernelNotLoadedError: 当内核加载失败时（目录不存在、文件损坏等）
            ValueError: 当 kernel_id 未知（没有对应实现类）时
        """
        # 根据 kernel_id 选择对应的实现类
        # 后续新增内核时，在此处扩展 if-elif 分支
        if kernel_id == "skill-creator":
            impl = SkillCreatorKernelImpl(kernel_path)
        else:
            # 未知内核 ID：这是一个开发时错误，不是运行时错误
            raise ValueError(
                f"未知的内核 ID: {kernel_id}，"
                "请在 KernelRegistry.load_kernel() 中添加对应的实现类"
            )

        with self._instance_lock:
            self._kernels[kernel_id] = impl

        return impl

    def get_kernel(self, kernel_id: str = "skill-creator") -> KernelAdapter:
        """
        获取已注册的内核实例。

        Args:
            kernel_id: 内核唯一标识符，默认为 "skill-creator"

        Returns:
            对应的 KernelAdapter 实例。

        Raises:
            KernelNotFoundError: 当指定的 kernel_id 未注册时
        """
        with self._instance_lock:
            kernel = self._kernels.get(kernel_id)

        if kernel is None:
            raise KernelNotFoundError(
                f"内核 '{kernel_id}' 未注册，请确认内核已成功加载"
            )
        return kernel

    def list_kernels(self) -> List[KernelMeta]:
        """
        列出所有已注册内核的元数据。

        Returns:
            KernelMeta 对象列表。
        """
        with self._instance_lock:
            return [kernel.get_kernel_meta() for kernel in self._kernels.values()]

    def is_loaded(self, kernel_id: str) -> bool:
        """
        检查指定内核是否已加载。

        Args:
            kernel_id: 内核唯一标识符

        Returns:
            True 表示已加载，False 表示未加载。
        """
        with self._instance_lock:
            return kernel_id in self._kernels

    def reload_kernel(self, kernel_id: str, kernel_path: str) -> KernelAdapter:
        """
        重新加载已注册的内核（用于内核升级或热更新）。

        重新加载成功后，旧的内核实例会被替换，
        后续所有通过 get_kernel() 获取的实例都是新版本。

        Args:
            kernel_id: 内核唯一标识符
            kernel_path: 内核目录的绝对路径（新版本路径）

        Returns:
            重新加载后的 KernelAdapter 实例。
        """
        # 直接调用 load_kernel，会覆盖已有注册
        return self.load_kernel(kernel_id, kernel_path)
