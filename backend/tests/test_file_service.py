"""
backend/tests/test_file_service.py

文件管理服务单元测试。

测试覆盖：
    - 路径安全校验（最重要的安全特性）
    - 文件读写操作
    - 目录树构建
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestFileServicePathSecurity:
    """FileService 路径安全校验测试（最高优先级）。"""

    @pytest.fixture
    def workspace_root(self, tmp_path):
        """创建临时工作区根目录。"""
        workspace = tmp_path / "workspace" / "test-task-id"
        workspace.mkdir(parents=True)
        return workspace

    @pytest.fixture
    def file_service_with_mock_task(self, workspace_root):
        """创建带 mock 任务的 FileService 实例。"""
        from app.services.file_service import FileService

        service = FileService()
        # Mock get_workspace_root 返回临时目录
        service.get_workspace_root = MagicMock(return_value=workspace_root)
        return service, workspace_root

    def test_path_traversal_blocked(self, file_service_with_mock_task):
        """测试路径遍历攻击（../../etc/passwd）被拒绝。"""
        from app.exceptions import PathSecurityError

        service, _ = file_service_with_mock_task
        with pytest.raises(PathSecurityError):
            service._safe_resolve("task-id", "../../etc/passwd")

    def test_absolute_path_blocked(self, file_service_with_mock_task):
        """测试绝对路径访问被拒绝。"""
        from app.exceptions import PathSecurityError

        service, _ = file_service_with_mock_task
        with pytest.raises(PathSecurityError):
            service._safe_resolve("task-id", "/etc/passwd")

    def test_valid_path_allowed(self, file_service_with_mock_task):
        """测试合法的相对路径被允许。"""
        service, workspace_root = file_service_with_mock_task
        target = service._safe_resolve("task-id", "my-skill/SKILL.md")
        assert str(target).startswith(str(workspace_root))

    def test_nested_path_allowed(self, file_service_with_mock_task):
        """测试嵌套目录路径被允许。"""
        service, workspace_root = file_service_with_mock_task
        target = service._safe_resolve("task-id", "my-skill/scripts/helper.py")
        assert str(target).startswith(str(workspace_root))

    def test_read_write_file(self, file_service_with_mock_task):
        """测试文件写入和读取。"""
        from unittest.mock import patch

        service, workspace_root = file_service_with_mock_task

        # Mock _log_file_op to avoid db dependency in unit test
        with patch.object(service, '_log_file_op', staticmethod=True) as mock_log:
            with patch('app.services.file_service.FileService._log_file_op', return_value=None):
                service.write_file("task-id", "test.md", "# Hello World")

        # 验证文件存在且内容正确
        file_path = workspace_root / "test.md"
        assert file_path.exists()
        assert file_path.read_text() == "# Hello World"

    def test_delete_file(self, file_service_with_mock_task):
        """测试文件删除。"""
        from unittest.mock import patch

        service, workspace_root = file_service_with_mock_task

        # 先创建文件
        test_file = workspace_root / "to-delete.txt"
        test_file.write_text("delete me")

        # 删除文件（mock db logging）
        with patch('app.services.file_service.FileService._log_file_op', return_value=None):
            service.delete_file("task-id", "to-delete.txt")
        assert not test_file.exists()
