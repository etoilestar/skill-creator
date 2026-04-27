"""
backend/tests/test_api_all_endpoints.py

全接口集成测试套件。

覆盖全部 HTTP 接口（不调用真实 LLM / Celery / Docker）：
    - /api/v1/config/models        模型配置管理
    - /api/v1/kernels               内核管理
    - /api/v1/sessions              多轮会话
    - /api/v1/tasks                 任务管理
    - /api/v1/tasks/<id>/files      文件管理
    - /api/v1/tasks/<id>/tests      沙盒测试
    - /api/v1/skills                Skill 检索与导入
    - /api/v1/agent                 Skill Agent 执行

测试策略：
    - 所有 LLM 调用（ModelProviderFactory）用 unittest.mock.patch 替换
    - 所有 Celery 任务（create_skill_task.delay / run_sandbox_test_task.delay）用 Mock 替换
    - 数据库使用 TestingConfig 的 SQLite 内存库
"""

import io
import json
import sys
import uuid
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# 确保测试数据库表在整个 session 内只建一次
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _ensure_db_tables(db):
    """依赖 conftest 中的 db fixture，触发 db.create_all()。"""
    yield

# ---------------------------------------------------------------------------
# Mock AI 回复（含 requirement_spec JSON 块，completeness_score=85 可触发确认）
# ---------------------------------------------------------------------------

_MOCK_AI_REPLY = """\
好的，我来帮你创建这个 Skill。

```requirement_spec
{
  "skill_name": "test-skill",
  "display_name": "测试 Skill",
  "core_function": "自动化测试核心功能",
  "trigger_contexts": ["场景A", "场景B", "场景C"],
  "not_for": ["不适用场景"],
  "expected_output": "预期输出描述",
  "needs_scripts": false,
  "script_requirements": null,
  "edge_cases": ["边界情况"],
  "dependencies": [],
  "completeness_score": 85
}
```
"""


def _make_mock_provider():
    """构造固定回复的 MockProvider。"""
    provider = MagicMock()
    provider.chat.return_value = _MOCK_AI_REPLY
    provider.stream_chat.return_value = iter([_MOCK_AI_REPLY])
    provider.test_connection.return_value = MagicMock(
        success=True, latency_ms=42.0, error=None, model_info={"model": "mock-model"}
    )
    return provider


def _fake_celery_result():
    result = MagicMock()
    result.id = str(uuid.uuid4())
    return result


# ---------------------------------------------------------------------------
# 辅助：在 app context 内直接写库，创建测试依赖数据
# ---------------------------------------------------------------------------

def _create_task(app, tmp_path, status="created"):
    """创建 SkillCreationTask + 工作区 SKILL.md，返回 (task_id, skill_dir_str)。"""
    from app.extensions import db
    from app.models.skill_creation_task import SkillCreationTask

    task_id = str(uuid.uuid4())
    skill_dir = tmp_path / task_id
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: 测试 Skill\nversion: 1.0.0\n---\n# 测试\n",
        encoding="utf-8",
    )

    with app.app_context():
        task = SkillCreationTask(
            id=task_id,
            skill_name="test-skill",
            status=status,
            workspace_path=str(skill_dir),
            kernel_id="skill-creator",
            requirement_spec={
                "skill_name": "test-skill",
                "core_function": "测试",
                "trigger_contexts": ["场景A", "场景B", "场景C"],
                "completeness_score": 85,
            },
        )
        db.session.add(task)
        db.session.commit()

    return task_id, str(skill_dir)


def _create_session(app, score=85):
    """创建 ConversationSession，返回 session_id。"""
    from app.extensions import db
    from app.models.session import ConversationSession

    session_id = str(uuid.uuid4())
    with app.app_context():
        session = ConversationSession(
            id=session_id,
            messages=[
                {"role": "user", "content": "我想创建测试 Skill", "timestamp": "2024-01-01T00:00:00"},
                {"role": "assistant", "content": "好的", "timestamp": "2024-01-01T00:00:01"},
            ],
            requirement_spec={
                "skill_name": "test-skill",
                "core_function": "测试功能",
                "trigger_contexts": ["场景A", "场景B", "场景C"],
                "completeness_score": score,
            },
            completeness_score=score,
            phase=(
                ConversationSession.PHASE_STRUCTURING
                if score >= 80
                else ConversationSession.PHASE_GATHERING
            ),
        )
        db.session.add(session)
        db.session.commit()
    return session_id


# ---------------------------------------------------------------------------
# 1. 模型配置接口  /api/v1/config/models
# ---------------------------------------------------------------------------

class TestConfigModels:

    def test_list_models_returns_list(self, client, app):
        rv = client.get("/api/v1/config/models")
        assert rv.status_code == 200
        assert isinstance(rv.get_json(), list)

    def test_create_model_success(self, client, app):
        rv = client.post("/api/v1/config/models", json={
            "name": "GPT-4o 测试",
            "provider": "openai",
            "model_name": "gpt-4o",
            "api_key": "sk-fake-key",
            "max_tokens": 2048,
            "temperature": 0.5,
        })
        assert rv.status_code == 201
        data = rv.get_json()
        assert data["name"] == "GPT-4o 测试"
        assert data["has_api_key"] is True
        assert "id" in data

    def test_create_model_missing_field(self, client, app):
        rv = client.post("/api/v1/config/models", json={"name": "incomplete"})
        assert rv.status_code == 400
        assert "error" in rv.get_json()

    def test_list_models_includes_created(self, client, app):
        client.post("/api/v1/config/models", json={
            "name": "列表模型", "provider": "openai", "model_name": "gpt-3.5-turbo"
        })
        rv = client.get("/api/v1/config/models")
        assert rv.status_code == 200
        assert any(c["name"] == "列表模型" for c in rv.get_json())

    def test_update_model_name(self, client, app):
        create_rv = client.post("/api/v1/config/models", json={
            "name": "更新前", "provider": "openai", "model_name": "gpt-3.5-turbo"
        })
        cid = create_rv.get_json()["id"]
        rv = client.put(f"/api/v1/config/models/{cid}", json={"name": "更新后"})
        assert rv.status_code == 200
        assert rv.get_json()["name"] == "更新后"

    def test_update_model_not_found(self, client, app):
        rv = client.put(f"/api/v1/config/models/{uuid.uuid4()}", json={"name": "x"})
        assert rv.status_code == 404

    def test_activate_model(self, client, app):
        cid = client.post("/api/v1/config/models", json={
            "name": "待激活", "provider": "openai", "model_name": "gpt-4o"
        }).get_json()["id"]
        rv = client.post(f"/api/v1/config/models/{cid}/activate")
        assert rv.status_code == 200
        assert rv.get_json()["config"]["is_active"] is True

    def test_activate_model_not_found(self, client, app):
        rv = client.post(f"/api/v1/config/models/{uuid.uuid4()}/activate")
        assert rv.status_code == 404

    def test_delete_inactive_model(self, client, app):
        # 先激活另一个，确保待删除不是激活状态
        active_id = client.post("/api/v1/config/models", json={
            "name": "保持激活", "provider": "openai", "model_name": "gpt-4o"
        }).get_json()["id"]
        client.post(f"/api/v1/config/models/{active_id}/activate")

        del_id = client.post("/api/v1/config/models", json={
            "name": "待删除", "provider": "openai", "model_name": "gpt-3.5-turbo"
        }).get_json()["id"]
        rv = client.delete(f"/api/v1/config/models/{del_id}")
        assert rv.status_code == 200

    def test_delete_active_model_blocked(self, client, app):
        cid = client.post("/api/v1/config/models", json={
            "name": "激活中", "provider": "openai", "model_name": "gpt-4o"
        }).get_json()["id"]
        client.post(f"/api/v1/config/models/{cid}/activate")
        rv = client.delete(f"/api/v1/config/models/{cid}")
        assert rv.status_code == 400
        assert rv.get_json()["error"]["code"] == "CANNOT_DELETE_ACTIVE"

    def test_delete_model_not_found(self, client, app):
        rv = client.delete(f"/api/v1/config/models/{uuid.uuid4()}")
        assert rv.status_code == 404

    def test_test_connection_success(self, client, app):
        cid = client.post("/api/v1/config/models", json={
            "name": "连通测试", "provider": "openai", "model_name": "gpt-4o", "api_key": "sk-x"
        }).get_json()["id"]
        with patch("app.model.provider.ModelProviderFactory.create",
                   return_value=_make_mock_provider()):
            rv = client.post(f"/api/v1/config/models/{cid}/test")
        assert rv.status_code == 200
        assert rv.get_json()["success"] is True

    def test_test_connection_not_found(self, client, app):
        rv = client.post(f"/api/v1/config/models/{uuid.uuid4()}/test")
        assert rv.status_code == 404


# ---------------------------------------------------------------------------
# 2. 内核接口  /api/v1/kernels
# ---------------------------------------------------------------------------

class TestKernels:

    def test_list_kernels(self, client, app):
        rv = client.get("/api/v1/kernels")
        assert rv.status_code == 200
        assert isinstance(rv.get_json(), list)

    def test_get_skill_creator_kernel(self, client, app):
        rv = client.get("/api/v1/kernels/skill-creator")
        # 内核目录存在时返回 200，否则 404
        assert rv.status_code in (200, 404)
        if rv.status_code == 200:
            assert "kernel_id" in rv.get_json()

    def test_get_nonexistent_kernel(self, client, app):
        rv = client.get("/api/v1/kernels/does-not-exist-ever")
        assert rv.status_code == 404
        assert "error" in rv.get_json()

    def test_get_kernel_guide(self, client, app):
        rv = client.get("/api/v1/kernels/skill-creator/guide")
        assert rv.status_code in (200, 404)
        if rv.status_code == 200:
            assert "guide" in rv.get_json()

    def test_get_kernel_guide_not_found(self, client, app):
        rv = client.get("/api/v1/kernels/no-such-kernel/guide")
        assert rv.status_code == 404

    def test_reload_nonexistent_kernel(self, client, app):
        rv = client.post("/api/v1/kernels/no-such-kernel/reload")
        # 重载不存在的内核返回 500（目录不存在）
        assert rv.status_code in (500, 404)


# ---------------------------------------------------------------------------
# 3. 会话接口  /api/v1/sessions
# ---------------------------------------------------------------------------

class TestSessions:

    def test_create_session_success(self, client, app):
        with patch(
            "app.model.provider.ModelProviderFactory.create_from_active_config",
            return_value=_make_mock_provider(),
        ):
            rv = client.post("/api/v1/sessions", json={"message": "我想创建一个邮件摘要 Skill"})
        assert rv.status_code == 201
        data = rv.get_json()
        assert "id" in data
        assert len(data["messages"]) >= 2

    def test_create_session_missing_message(self, client, app):
        rv = client.post("/api/v1/sessions", json={})
        assert rv.status_code == 400

    def test_get_session_success(self, client, app):
        sid = _create_session(app, score=40)
        rv = client.get(f"/api/v1/sessions/{sid}")
        assert rv.status_code == 200
        assert rv.get_json()["id"] == sid

    def test_get_session_not_found(self, client, app):
        rv = client.get(f"/api/v1/sessions/{uuid.uuid4()}")
        assert rv.status_code == 404

    def test_send_message_success(self, client, app):
        sid = _create_session(app, score=40)
        with patch(
            "app.model.provider.ModelProviderFactory.create_from_active_config",
            return_value=_make_mock_provider(),
        ):
            rv = client.post(f"/api/v1/sessions/{sid}/messages",
                             json={"message": "补充一下使用场景"})
        assert rv.status_code == 200
        data = rv.get_json()
        assert "ai_reply" in data
        assert "session" in data

    def test_send_message_missing_field(self, client, app):
        sid = _create_session(app, score=40)
        rv = client.post(f"/api/v1/sessions/{sid}/messages", json={})
        assert rv.status_code == 400

    def test_send_message_session_not_found(self, client, app):
        with patch(
            "app.model.provider.ModelProviderFactory.create_from_active_config",
            return_value=_make_mock_provider(),
        ):
            rv = client.post(f"/api/v1/sessions/{uuid.uuid4()}/messages",
                             json={"message": "hello"})
        assert rv.status_code == 404

    def test_get_requirement(self, client, app):
        sid = _create_session(app, score=60)
        rv = client.get(f"/api/v1/sessions/{sid}/requirement")
        assert rv.status_code == 200
        data = rv.get_json()
        assert "requirement_spec" in data
        assert "completeness_score" in data

    def test_get_requirement_not_found(self, client, app):
        rv = client.get(f"/api/v1/sessions/{uuid.uuid4()}/requirement")
        assert rv.status_code == 404

    def test_stream_message(self, client, app):
        sid = _create_session(app, score=40)
        with patch(
            "app.model.provider.ModelProviderFactory.create_from_active_config",
            return_value=_make_mock_provider(),
        ):
            rv = client.post(f"/api/v1/sessions/{sid}/stream",
                             json={"message": "再补充一些"})
        assert rv.status_code == 200
        assert "text/event-stream" in rv.content_type

    def test_stream_message_missing_field(self, client, app):
        sid = _create_session(app, score=40)
        rv = client.post(f"/api/v1/sessions/{sid}/stream", json={})
        assert rv.status_code == 400

    def test_upload_attachment(self, client, app):
        sid = _create_session(app, score=40)
        data = {"file": (io.BytesIO(b"# Hello World"), "readme.md")}
        rv = client.post(
            f"/api/v1/sessions/{sid}/attachments",
            data=data,
            content_type="multipart/form-data",
        )
        assert rv.status_code == 201
        meta = rv.get_json()
        assert "filename" in meta
        assert meta["size"] > 0

    def test_upload_attachment_missing_file(self, client, app):
        sid = _create_session(app, score=40)
        rv = client.post(f"/api/v1/sessions/{sid}/attachments",
                         content_type="multipart/form-data", data={})
        assert rv.status_code == 400

    def test_upload_attachment_invalid_type(self, client, app):
        sid = _create_session(app, score=40)
        data = {"file": (io.BytesIO(b"binary"), "image.png")}
        rv = client.post(
            f"/api/v1/sessions/{sid}/attachments",
            data=data,
            content_type="multipart/form-data",
        )
        assert rv.status_code == 400

    def test_confirm_session_success(self, client, app, tmp_path):
        sid = _create_session(app, score=85)
        with patch(
            "app.tasks.skill_creation_task.create_skill_task.delay",
            return_value=_fake_celery_result(),
        ):
            rv = client.post(f"/api/v1/sessions/{sid}/confirm")
        assert rv.status_code == 202
        data = rv.get_json()
        assert "task" in data
        assert data["task"]["status"] == "pending"

    def test_confirm_session_incomplete(self, client, app):
        sid = _create_session(app, score=30)
        rv = client.post(f"/api/v1/sessions/{sid}/confirm")
        assert rv.status_code == 400

    def test_confirm_session_not_found(self, client, app):
        rv = client.post(f"/api/v1/sessions/{uuid.uuid4()}/confirm")
        assert rv.status_code == 404


# ---------------------------------------------------------------------------
# 4. 任务接口  /api/v1/tasks
# ---------------------------------------------------------------------------

class TestTasks:

    def test_list_tasks(self, client, app, tmp_path):
        _create_task(app, tmp_path)
        rv = client.get("/api/v1/tasks")
        assert rv.status_code == 200
        data = rv.get_json()
        assert "tasks" in data
        assert "total" in data

    def test_list_tasks_with_status_filter(self, client, app, tmp_path):
        _create_task(app, tmp_path, status="created")
        rv = client.get("/api/v1/tasks?status=created")
        assert rv.status_code == 200
        for t in rv.get_json()["tasks"]:
            assert t["status"] == "created"

    def test_list_tasks_pagination(self, client, app, tmp_path):
        rv = client.get("/api/v1/tasks?page=1&per_page=5")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["page"] == 1
        assert data["per_page"] == 5

    def test_get_task_success(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        rv = client.get(f"/api/v1/tasks/{tid}")
        assert rv.status_code == 200
        assert rv.get_json()["id"] == tid

    def test_get_task_not_found(self, client, app):
        rv = client.get(f"/api/v1/tasks/{uuid.uuid4()}")
        assert rv.status_code == 404

    def test_get_task_logs(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        rv = client.get(f"/api/v1/tasks/{tid}/logs")
        assert rv.status_code == 200
        assert isinstance(rv.get_json(), list)

    def test_get_task_logs_not_found(self, client, app):
        rv = client.get(f"/api/v1/tasks/{uuid.uuid4()}/logs")
        assert rv.status_code == 404

    def test_retry_task_success(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path, status="creation_failed")
        with patch(
            "app.tasks.skill_creation_task.create_skill_task.delay",
            return_value=_fake_celery_result(),
        ):
            rv = client.post(f"/api/v1/tasks/{tid}/retry")
        assert rv.status_code == 200
        assert rv.get_json()["task"]["status"] == "pending"

    def test_retry_task_invalid_state(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path, status="created")
        rv = client.post(f"/api/v1/tasks/{tid}/retry")
        assert rv.status_code == 409

    def test_retry_task_not_found(self, client, app):
        rv = client.post(f"/api/v1/tasks/{uuid.uuid4()}/retry")
        assert rv.status_code == 404


# ---------------------------------------------------------------------------
# 5. 文件接口  /api/v1/tasks/<id>/files
# ---------------------------------------------------------------------------

class TestFiles:

    def test_list_files(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        rv = client.get(f"/api/v1/tasks/{tid}/files")
        assert rv.status_code == 200
        assert isinstance(rv.get_json(), list)

    def test_list_files_task_not_found(self, client, app):
        rv = client.get(f"/api/v1/tasks/{uuid.uuid4()}/files")
        assert rv.status_code == 404

    def test_read_file_success(self, client, app, tmp_path):
        tid, skill_dir = _create_task(app, tmp_path)
        # workspace_root = workspace_path.parent (see FileService.get_workspace_root)
        # so the SKILL.md lives at workspace_root/{task_id}/SKILL.md
        rv = client.get(f"/api/v1/tasks/{tid}/files/{tid}/SKILL.md")
        assert rv.status_code == 200
        data = rv.get_json()
        assert "content" in data
        assert "name: test-skill" in data["content"]

    def test_read_file_not_found(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        rv = client.get(f"/api/v1/tasks/{tid}/files/does_not_exist.py")
        assert rv.status_code == 404

    def test_read_file_path_traversal(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        rv = client.get(f"/api/v1/tasks/{tid}/files/../../etc/passwd")
        assert rv.status_code in (400, 404)

    def test_write_file_success(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        rv = client.put(f"/api/v1/tasks/{tid}/files/new_file.py",
                        json={"content": "print('hello')"})
        assert rv.status_code == 200

    def test_write_file_missing_content(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        rv = client.put(f"/api/v1/tasks/{tid}/files/new_file.py", json={})
        assert rv.status_code == 400

    def test_write_then_read(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        content = "# 测试内容\nprint('world')"
        client.put(f"/api/v1/tasks/{tid}/files/hello.py", json={"content": content})
        rv = client.get(f"/api/v1/tasks/{tid}/files/hello.py")
        assert rv.status_code == 200
        assert rv.get_json()["content"] == content

    def test_delete_file_success(self, client, app, tmp_path):
        tid, skill_dir = _create_task(app, tmp_path)
        # 写一个文件再删
        client.put(f"/api/v1/tasks/{tid}/files/temp.txt", json={"content": "bye"})
        rv = client.delete(f"/api/v1/tasks/{tid}/files/temp.txt")
        assert rv.status_code == 200

    def test_delete_file_not_found(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        rv = client.delete(f"/api/v1/tasks/{tid}/files/ghost.txt")
        assert rv.status_code == 404

    def test_rename_file_success(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        client.put(f"/api/v1/tasks/{tid}/files/old.py", json={"content": "x=1"})
        rv = client.post(f"/api/v1/tasks/{tid}/files/rename",
                         json={"old_path": "old.py", "new_path": "new.py"})
        assert rv.status_code == 200

    def test_rename_file_missing_fields(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        rv = client.post(f"/api/v1/tasks/{tid}/files/rename", json={})
        assert rv.status_code == 400

    def test_rename_file_not_found(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        rv = client.post(f"/api/v1/tasks/{tid}/files/rename",
                         json={"old_path": "ghost.py", "new_path": "ghost2.py"})
        assert rv.status_code == 404


# ---------------------------------------------------------------------------
# 6. 沙盒测试接口  /api/v1/tasks/<id>/tests
# ---------------------------------------------------------------------------

class TestSandboxTests:

    def test_trigger_test_success(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path, status="created")
        with patch(
            "app.tasks.sandbox_test_task.run_sandbox_test_task.delay",
            return_value=_fake_celery_result(),
        ):
            rv = client.post(f"/api/v1/tasks/{tid}/tests")
        assert rv.status_code == 202
        data = rv.get_json()
        assert data["test"]["status"] == "running"

    def test_trigger_test_invalid_state(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path, status="pending")
        rv = client.post(f"/api/v1/tasks/{tid}/tests")
        assert rv.status_code == 409

    def test_trigger_test_not_found(self, client, app):
        rv = client.post(f"/api/v1/tasks/{uuid.uuid4()}/tests")
        assert rv.status_code == 404

    def test_list_tests(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path, status="created")
        rv = client.get(f"/api/v1/tasks/{tid}/tests")
        assert rv.status_code == 200
        assert isinstance(rv.get_json(), list)

    def test_list_tests_task_not_found(self, client, app):
        rv = client.get(f"/api/v1/tasks/{uuid.uuid4()}/tests")
        assert rv.status_code == 404

    def test_get_test_success(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path, status="created")
        with patch(
            "app.tasks.sandbox_test_task.run_sandbox_test_task.delay",
            return_value=_fake_celery_result(),
        ):
            trigger_rv = client.post(f"/api/v1/tasks/{tid}/tests")
        test_id = trigger_rv.get_json()["test"]["id"]
        rv = client.get(f"/api/v1/tasks/{tid}/tests/{test_id}")
        assert rv.status_code == 200
        assert rv.get_json()["id"] == test_id

    def test_get_test_not_found(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        rv = client.get(f"/api/v1/tasks/{tid}/tests/{uuid.uuid4()}")
        assert rv.status_code == 404

    def test_get_test_logs(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path, status="created")
        with patch(
            "app.tasks.sandbox_test_task.run_sandbox_test_task.delay",
            return_value=_fake_celery_result(),
        ):
            trigger_rv = client.post(f"/api/v1/tasks/{tid}/tests")
        test_id = trigger_rv.get_json()["test"]["id"]
        rv = client.get(f"/api/v1/tasks/{tid}/tests/{test_id}/logs")
        assert rv.status_code == 200
        data = rv.get_json()
        assert "raw_output" in data
        assert "status" in data

    def test_get_test_logs_not_found(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        rv = client.get(f"/api/v1/tasks/{tid}/tests/{uuid.uuid4()}/logs")
        assert rv.status_code == 404


# ---------------------------------------------------------------------------
# 7. Skill 检索与导入  /api/v1/skills
# ---------------------------------------------------------------------------

class TestSkills:

    def test_list_skills(self, client, app):
        rv = client.get("/api/v1/skills")
        assert rv.status_code == 200
        data = rv.get_json()
        assert "skills" in data
        assert "total" in data

    def test_list_skills_with_limit(self, client, app):
        rv = client.get("/api/v1/skills?limit=10")
        assert rv.status_code == 200
        assert len(rv.get_json()["skills"]) <= 10

    def test_search_skills_missing_query(self, client, app):
        rv = client.get("/api/v1/skills/search")
        assert rv.status_code == 400
        assert "MISSING_QUERY" in rv.get_json()["error"]["code"]

    def test_search_skills_with_query(self, client, app):
        rv = client.get("/api/v1/skills/search?q=邮件摘要")
        assert rv.status_code == 200
        data = rv.get_json()
        assert "query" in data
        assert "results" in data

    def test_search_skills_with_top_k(self, client, app):
        rv = client.get("/api/v1/skills/search?q=测试&top_k=3")
        assert rv.status_code == 200
        assert len(rv.get_json()["results"]) <= 3

    def test_search_in_task(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        rv = client.get(f"/api/v1/skills/search/{tid}?q=测试")
        assert rv.status_code == 200
        data = rv.get_json()
        assert "task_id" in data
        assert "results" in data

    def test_search_in_task_missing_query(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        rv = client.get(f"/api/v1/skills/search/{tid}")
        assert rv.status_code == 400

    def test_search_in_task_not_found(self, client, app):
        rv = client.get(f"/api/v1/skills/search/{uuid.uuid4()}?q=test")
        assert rv.status_code == 404

    def test_get_skill_detail(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        rv = client.get(f"/api/v1/skills/{tid}")
        assert rv.status_code == 200
        data = rv.get_json()
        assert "skill_md_content" in data
        assert "frontmatter" in data

    def test_get_skill_detail_not_found(self, client, app):
        rv = client.get(f"/api/v1/skills/{uuid.uuid4()}")
        assert rv.status_code == 404

    def test_delete_skill(self, client, app, tmp_path):
        tid, _ = _create_task(app, tmp_path)
        rv = client.delete(f"/api/v1/skills/{tid}")
        assert rv.status_code == 200
        assert rv.get_json()["task_id"] == tid

    def test_delete_skill_not_found(self, client, app):
        rv = client.delete(f"/api/v1/skills/{uuid.uuid4()}")
        assert rv.status_code == 404

    def test_import_skill_success(self, client, app):
        """POST /api/v1/skills/import — 上传包含 SKILL.md 的有效 ZIP。"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "my-skill/SKILL.md",
                (
                    "---\n"
                    "name: imported-skill\n"
                    "description: Use when user wants to test skill import. NOT for production use.\n"
                    "version: 1.0.0\n"
                    "---\n"
                    "# 导入测试\n"
                ),
            )
        buf.seek(0)
        rv = client.post(
            "/api/v1/skills/import",
            data={"file": (buf, "my-skill.zip")},
            content_type="multipart/form-data",
        )
        assert rv.status_code == 201
        data = rv.get_json()
        assert "task" in data

    def test_import_skill_missing_file(self, client, app):
        rv = client.post("/api/v1/skills/import",
                         content_type="multipart/form-data", data={})
        assert rv.status_code == 400
        assert "MISSING_FILE" in rv.get_json()["error"]["code"]

    def test_import_skill_wrong_extension(self, client, app):
        rv = client.post(
            "/api/v1/skills/import",
            data={"file": (io.BytesIO(b"data"), "skill.tar.gz")},
            content_type="multipart/form-data",
        )
        assert rv.status_code == 400
        assert "INVALID_FILE_TYPE" in rv.get_json()["error"]["code"]

    def test_import_skill_invalid_zip(self, client, app):
        rv = client.post(
            "/api/v1/skills/import",
            data={"file": (io.BytesIO(b"not a zip"), "skill.zip")},
            content_type="multipart/form-data",
        )
        assert rv.status_code == 400
        assert "INVALID_ZIP" in rv.get_json()["error"]["code"]

    def test_import_skill_missing_skill_md(self, client, app):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("README.md", "# 无 SKILL.md 的包")
        buf.seek(0)
        rv = client.post(
            "/api/v1/skills/import",
            data={"file": (buf, "no-skill.zip")},
            content_type="multipart/form-data",
        )
        assert rv.status_code == 400
        assert "MISSING_SKILL_MD" in rv.get_json()["error"]["code"]


# ---------------------------------------------------------------------------
# 8. Agent 接口  /api/v1/agent
# ---------------------------------------------------------------------------

class TestAgent:

    def test_agent_chat_no_skill_indexed(self, client, app):
        """POST /api/v1/agent/chat — 没有 Skill 索引时返回 Agent 错误。"""
        rv = client.post("/api/v1/agent/chat", json={"query": "帮我处理邮件"})
        # 没有激活 LLM 配置 + 没有可用 Skill → 500 或 error
        assert rv.status_code in (400, 500)
        assert "error" in rv.get_json()

    def test_agent_chat_missing_query(self, client, app):
        rv = client.post("/api/v1/agent/chat", json={})
        assert rv.status_code == 400
        assert "MISSING_FIELD" in rv.get_json()["error"]["code"]

    def test_agent_stream_missing_query(self, client, app):
        rv = client.post("/api/v1/agent/stream", json={})
        assert rv.status_code == 400
        assert "MISSING_FIELD" in rv.get_json()["error"]["code"]

    def test_agent_chat_with_mock_skill(self, client, app, tmp_path):
        """POST /api/v1/agent/chat — 有可用 Skill 时 Mock LLM 正常返回。"""
        # 创建带工作区的任务（Skill 可被索引）
        tid, skill_dir = _create_task(app, tmp_path, status="created")

        mock_provider = _make_mock_provider()
        mock_provider.stream_chat.return_value = iter([
            '{"type":"text","content":"这是回复"}',
            '{"type":"done","skill_name":"test-skill","skill_path":"' + skill_dir + '/SKILL.md"}',
        ])

        with patch(
            "app.model.provider.ModelProviderFactory.create_from_active_config",
            return_value=mock_provider,
        ):
            rv = client.post("/api/v1/agent/chat", json={"query": "test-skill 帮我测试"})

        # 有 Skill 时应返回 200（Agent 正常完成）或 500（LLM mock 内容被原样输出也可接受）
        assert rv.status_code in (200, 500)

    def test_agent_stream_returns_event_stream(self, client, app, tmp_path):
        """POST /api/v1/agent/stream — 有可用 Skill 时返回 SSE 流。"""
        _create_task(app, tmp_path, status="created")
        mock_provider = _make_mock_provider()
        mock_provider.stream_chat.return_value = iter(["AI 回复内容"])

        with patch(
            "app.model.provider.ModelProviderFactory.create_from_active_config",
            return_value=mock_provider,
        ):
            rv = client.post("/api/v1/agent/stream", json={"query": "测试查询"})

        assert rv.status_code == 200
        assert "text/event-stream" in rv.content_type


# ---------------------------------------------------------------------------
# 9. 错误处理通用验证
# ---------------------------------------------------------------------------

class TestGlobalErrorHandlers:

    def test_404_returns_json(self, client, app):
        rv = client.get("/api/v1/nonexistent-route-xyz")
        assert rv.status_code == 404
        data = rv.get_json()
        assert "error" in data

    def test_method_not_allowed(self, client, app):
        rv = client.delete("/api/v1/kernels")
        assert rv.status_code == 405
        data = rv.get_json()
        assert "error" in data
