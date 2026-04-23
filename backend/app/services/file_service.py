"""
backend/app/services/file_service.py

Skill 文件管理服务。

职责：
    - 对工作区中的 Skill 文件执行读取、写入、删除、重命名操作
    - 严格执行路径安全校验，防止路径遍历攻击（Path Traversal）
    - 维护目录树结构，支持前端文件浏览器展示
    - 记录所有文件操作日志

路径安全约束（最高优先级，任何情况下不得绕过）：
    - 所有文件操作都限制在 WORKSPACE_BASE_PATH/{task_id}/ 内
    - 通过 Path.resolve() + 前缀校验实现路径边界检查
    - 禁止任何包含 ../ 的相对路径逃逸
    - 禁止直接访问绝对路径

目录隔离规范：
    - backend/kernels/ 目录：只读，绝不允许通过文件服务访问
    - backend/app/workspace/{task_id}/：用户 Skill 工作区（可读写）
    - backend/app/sandboxes/：沙盒测试区（由 SandboxService 管理）
"""

import os
from pathlib import Path
from typing import Dict, List, Optional

from ..exceptions import (
    FileWriteError,
    PathSecurityError,
    TaskNotFoundError,
    WorkspaceFileNotFoundError,
)
from ..extensions import db
from ..models.skill_creation_task import SkillCreationTask
from ..models.task_event_log import TaskEventLog


class FileNode:
    """
    文件系统节点，表示一个文件或目录。

    Attributes:
        name: 文件/目录名称
        path: 相对于 Skill 工作区根的路径
        is_dir: 是否为目录
        size: 文件大小（字节，目录为 None）
        children: 子节点列表（只有目录才有）
    """

    def __init__(
        self,
        name: str,
        path: str,
        is_dir: bool,
        size: Optional[int] = None,
        children: Optional[List["FileNode"]] = None,
    ):
        self.name = name
        self.path = path
        self.is_dir = is_dir
        self.size = size
        self.children = children or []

    def to_dict(self) -> dict:
        """序列化为字典。"""
        result = {
            "name": self.name,
            "path": self.path,
            "is_dir": self.is_dir,
            "size": self.size,
        }
        if self.is_dir:
            result["children"] = [c.to_dict() for c in self.children]
        return result


class FileService:
    """
    Skill 文件管理服务类。

    提供对用户 Skill 工作区文件的完整 CRUD 操作，
    所有操作都经过严格的路径安全校验。
    """

    def get_workspace_root(self, task_id: str) -> Path:
        """
        获取指定任务的工作区根目录路径。

        Args:
            task_id: SkillCreationTask ID

        Returns:
            工作区根目录的 Path 对象。

        Raises:
            TaskNotFoundError: 当任务不存在或工作区未初始化时
        """
        task = SkillCreationTask.query.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"任务不存在: {task_id}")
        if not task.workspace_path:
            raise TaskNotFoundError(
                f"任务 {task_id} 的工作区尚未初始化，请先完成 Skill 创建"
            )
        return Path(task.workspace_path).parent  # workspace/{task_id}/ 层

    def list_files(self, task_id: str) -> List[FileNode]:
        """
        获取指定任务工作区的文件目录树。

        返回工作区根目录下的所有文件和目录（递归），
        结果以树形结构表示，便于前端文件浏览器展示。

        Args:
            task_id: SkillCreationTask ID

        Returns:
            FileNode 列表（只包含根目录的直接子节点，节点内含子目录）。
        """
        workspace_root = self.get_workspace_root(task_id)
        if not workspace_root.exists():
            return []
        return self._build_file_tree(workspace_root, workspace_root)

    def read_file(self, task_id: str, relative_path: str) -> str:
        """
        读取工作区中指定文件的内容。

        Args:
            task_id: SkillCreationTask ID
            relative_path: 相对于工作区根目录的文件路径

        Returns:
            文件内容字符串（UTF-8 编码）。

        Raises:
            PathSecurityError: 当路径超出工作区边界时
            WorkspaceFileNotFoundError: 当文件不存在时
        """
        target = self._safe_resolve(task_id, relative_path)

        if not target.exists():
            raise WorkspaceFileNotFoundError(f"文件不存在: {relative_path}")
        if target.is_dir():
            raise WorkspaceFileNotFoundError(f"{relative_path} 是目录，不是文件")

        return target.read_text(encoding="utf-8")

    def write_file(self, task_id: str, relative_path: str, content: str) -> bool:
        """
        写入或更新工作区中指定文件的内容。

        如果文件不存在则创建，如果存在则覆盖。
        父目录不存在时自动创建。

        Args:
            task_id: SkillCreationTask ID
            relative_path: 相对于工作区根目录的文件路径
            content: 要写入的文件内容（UTF-8 编码）

        Returns:
            True 表示写入成功。

        Raises:
            PathSecurityError: 当路径超出工作区边界时
            FileWriteError: 当文件写入失败时
        """
        target = self._safe_resolve(task_id, relative_path)

        try:
            # 自动创建父目录
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as e:
            raise FileWriteError(f"文件写入失败 {relative_path}: {e}") from e

        # 记录文件操作日志
        self._log_file_op(task_id, "write", relative_path)
        return True

    def delete_file(self, task_id: str, relative_path: str) -> bool:
        """
        删除工作区中指定的文件或空目录。

        Args:
            task_id: SkillCreationTask ID
            relative_path: 相对于工作区根目录的文件路径

        Returns:
            True 表示删除成功。

        Raises:
            PathSecurityError: 当路径超出工作区边界时
            WorkspaceFileNotFoundError: 当文件不存在时
        """
        target = self._safe_resolve(task_id, relative_path)

        if not target.exists():
            raise WorkspaceFileNotFoundError(f"文件不存在: {relative_path}")

        try:
            if target.is_file():
                target.unlink()
            elif target.is_dir():
                # 只允许删除空目录（安全起见，不递归删除）
                target.rmdir()
        except OSError as e:
            raise FileWriteError(f"文件删除失败 {relative_path}: {e}") from e

        self._log_file_op(task_id, "delete", relative_path)
        return True

    def rename_file(
        self, task_id: str, old_path: str, new_path: str
    ) -> bool:
        """
        重命名工作区中的文件或目录。

        两个路径都必须在工作区边界内，否则拒绝操作。

        Args:
            task_id: SkillCreationTask ID
            old_path: 原始相对路径
            new_path: 新的相对路径

        Returns:
            True 表示重命名成功。

        Raises:
            PathSecurityError: 当任一路径超出工作区边界时
            WorkspaceFileNotFoundError: 当原文件不存在时
        """
        source = self._safe_resolve(task_id, old_path)
        dest = self._safe_resolve(task_id, new_path)

        if not source.exists():
            raise WorkspaceFileNotFoundError(f"文件不存在: {old_path}")

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            source.rename(dest)
        except OSError as e:
            raise FileWriteError(f"文件重命名失败 {old_path} -> {new_path}: {e}") from e

        self._log_file_op(task_id, "rename", old_path, {"new_path": new_path})
        return True

    def _safe_resolve(self, task_id: str, relative_path: str) -> Path:
        """
        安全路径解析：将相对路径解析为绝对路径，并严格校验是否在工作区内。

        这是文件服务最重要的安全措施，防止路径遍历攻击。
        通过 resolve() 展开所有 ../ 和符号链接，
        再检查解析后的路径是否以工作区根目录为前缀。

        Args:
            task_id: 任务 ID
            relative_path: 用户提供的相对路径（可能包含恶意内容）

        Returns:
            安全的目标路径 Path 对象。

        Raises:
            PathSecurityError: 当解析后路径超出工作区边界时
        """
        workspace_root = self.get_workspace_root(task_id).resolve()

        # 清理路径：去除首尾空白
        clean_path = relative_path.strip()

        # 明确拒绝绝对路径（包括 Unix / 和 Windows \ 开头）
        if clean_path.startswith("/") or (len(clean_path) >= 2 and clean_path[1] == ":"):
            raise PathSecurityError(
                f"非法路径访问：不允许使用绝对路径 '{relative_path}'"
            )

        clean_path = clean_path.lstrip("/\\")

        # 拼接并 realpath 展开所有 ../ 和符号链接
        try:
            combined = os.path.join(str(workspace_root), clean_path)
            resolved_str = os.path.realpath(combined)
        except Exception as e:
            raise PathSecurityError(f"路径解析失败: {relative_path}") from e

        # 关键安全检查：目标路径必须以工作区根路径为前缀
        workspace_str = str(workspace_root)

        if not (resolved_str == workspace_str or resolved_str.startswith(workspace_str + "/")):
            raise PathSecurityError(
                f"非法路径访问：操作路径 '{relative_path}' "
                "超出了工作区边界，操作已被拒绝"
            )

        # 安全检查通过后，从可信的 workspace_str 重建路径（而非来自用户输入），
        # 以破坏污点数据流并降低静态分析误报。
        safe_relative = resolved_str[len(workspace_str):].lstrip(os.sep)
        if safe_relative:
            return Path(workspace_str) / safe_relative
        return Path(workspace_str)

    def _build_file_tree(self, root: Path, base: Path) -> List[FileNode]:
        """
        递归构建文件目录树。

        Args:
            root: 当前要列出的目录路径
            base: 工作区根目录路径（用于计算相对路径）

        Returns:
            当前目录的 FileNode 列表。
        """
        nodes = []
        try:
            entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return nodes

        for entry in entries:
            rel_path = str(entry.relative_to(base))
            if entry.is_dir():
                children = self._build_file_tree(entry, base)
                nodes.append(FileNode(
                    name=entry.name,
                    path=rel_path,
                    is_dir=True,
                    children=children,
                ))
            else:
                nodes.append(FileNode(
                    name=entry.name,
                    path=rel_path,
                    is_dir=False,
                    size=entry.stat().st_size,
                ))
        return nodes

    @staticmethod
    def _log_file_op(
        task_id: str,
        operation: str,
        path: str,
        extra: Optional[dict] = None,
    ) -> None:
        """
        记录文件操作事件日志。

        Args:
            task_id: 任务 ID
            operation: 操作类型（read / write / delete / rename）
            path: 操作的文件路径
            extra: 额外信息（如重命名时的新路径）
        """
        event_data = {"operation": operation, "path": path}
        if extra:
            event_data.update(extra)
        log = TaskEventLog.log(task_id, TaskEventLog.ET_FILE_OPERATION, event_data)
        db.session.add(log)
        db.session.commit()
