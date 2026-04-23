"""
backend/app/kernel/__init__.py

内核适配层包初始化。
"""

from .base import KernelAdapter, KernelMeta, ValidationResult, ChecklistItem
from .registry import KernelRegistry
from .skill_creator_impl import SkillCreatorKernelImpl

__all__ = [
    "KernelAdapter",
    "KernelMeta",
    "ValidationResult",
    "ChecklistItem",
    "KernelRegistry",
    "SkillCreatorKernelImpl",
]
