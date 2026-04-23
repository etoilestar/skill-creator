"""
backend/tests/test_kernel_adapter.py

内核适配层单元测试。

测试覆盖：
    - skill-creator 内核加载
    - SKILL.md 内容读取
    - Skill 目录结构校验（合规/不合规场景）
    - eval 脚本路径获取
    - KernelRegistry 单例注册和查询
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

# 测试前确保能找到 backend/ 下的模块
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestSkillCreatorKernelImpl:
    """skill-creator 内核适配器单元测试。"""

    @pytest.fixture
    def kernel_path(self, tmp_path):
        """创建一个临时的完整内核目录结构。"""
        kernel_dir = tmp_path / "skill-creator"
        kernel_dir.mkdir()
        (kernel_dir / "scripts").mkdir()

        # 写入标准 SKILL.md
        (kernel_dir / "SKILL.md").write_text(
            """---
name: skill-creator
description: Create OpenClaw skills. Use when: (1) designing a new skill, (2) improving skill description. NOT for: non-skill tasks.
---

# Skill Creator
Create skills.
""",
            encoding="utf-8",
        )

        # 写入 kernel.json
        (kernel_dir / "kernel.json").write_text(
            json.dumps({
                "kernel_id": "skill-creator",
                "version": "1.0.0",
                "source_url": "https://skillsmp.com/...",
                "status": "active",
            }),
            encoding="utf-8",
        )

        # 写入 eval 脚本
        (kernel_dir / "scripts" / "eval_description.py").write_text(
            "# eval script\nprint('ok')\n", encoding="utf-8"
        )

        return str(kernel_dir)

    def test_load_kernel_success(self, kernel_path):
        """测试内核正常加载。"""
        from app.kernel.skill_creator_impl import SkillCreatorKernelImpl

        impl = SkillCreatorKernelImpl(kernel_path)
        meta = impl.get_kernel_meta()
        assert meta.kernel_id == "skill-creator"
        assert meta.version == "1.0.0"
        assert meta.status == "active"

    def test_load_kernel_missing_dir(self, tmp_path):
        """测试内核目录不存在时抛出 KernelNotLoadedError。"""
        from app.exceptions import KernelNotLoadedError
        from app.kernel.skill_creator_impl import SkillCreatorKernelImpl

        with pytest.raises(KernelNotLoadedError):
            SkillCreatorKernelImpl(str(tmp_path / "nonexistent"))

    def test_load_kernel_missing_skill_md(self, tmp_path):
        """测试 SKILL.md 不存在时抛出 KernelNotLoadedError。"""
        from app.exceptions import KernelNotLoadedError
        from app.kernel.skill_creator_impl import SkillCreatorKernelImpl

        empty_dir = tmp_path / "empty-kernel"
        empty_dir.mkdir()

        with pytest.raises(KernelNotLoadedError):
            SkillCreatorKernelImpl(str(empty_dir))

    def test_get_skill_creation_guide(self, kernel_path):
        """测试获取 SKILL.md 内容。"""
        from app.kernel.skill_creator_impl import SkillCreatorKernelImpl

        impl = SkillCreatorKernelImpl(kernel_path)
        guide = impl.get_skill_creation_guide()
        assert "skill-creator" in guide
        assert "Use when" in guide

    def test_validate_skill_structure_valid(self, kernel_path, tmp_path):
        """测试合规 Skill 目录通过校验。"""
        from app.kernel.skill_creator_impl import SkillCreatorKernelImpl

        impl = SkillCreatorKernelImpl(kernel_path)

        # 创建合规的 Skill 目录
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            """---
name: my-skill
description: Does something. Use when: user needs X. NOT for: other tasks.
---

# My Skill
""",
            encoding="utf-8",
        )

        result = impl.validate_skill_structure(str(skill_dir))
        assert result.valid is True
        assert len(result.errors) == 0

    def test_validate_skill_structure_missing_skill_md(self, kernel_path, tmp_path):
        """测试缺少 SKILL.md 时校验失败。"""
        from app.kernel.skill_creator_impl import SkillCreatorKernelImpl

        impl = SkillCreatorKernelImpl(kernel_path)
        empty_dir = tmp_path / "empty-skill"
        empty_dir.mkdir()

        result = impl.validate_skill_structure(str(empty_dir))
        assert result.valid is False
        assert any("SKILL.md" in e for e in result.errors)

    def test_validate_skill_structure_bad_name(self, kernel_path, tmp_path):
        """测试 name 不符合 kebab-case 规范时校验失败。"""
        from app.kernel.skill_creator_impl import SkillCreatorKernelImpl

        impl = SkillCreatorKernelImpl(kernel_path)
        skill_dir = tmp_path / "bad-name-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            """---
name: MySkill_WithBadName
description: Does something. Use when: needed.
---
""",
            encoding="utf-8",
        )

        result = impl.validate_skill_structure(str(skill_dir))
        assert result.valid is False
        assert any("kebab-case" in e for e in result.errors)

    def test_validate_skill_structure_missing_use_when(self, kernel_path, tmp_path):
        """测试 description 缺少 'Use when' 时校验失败。"""
        from app.kernel.skill_creator_impl import SkillCreatorKernelImpl

        impl = SkillCreatorKernelImpl(kernel_path)
        skill_dir = tmp_path / "no-use-when"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            """---
name: no-use-when
description: Just does something without trigger context.
---
""",
            encoding="utf-8",
        )

        result = impl.validate_skill_structure(str(skill_dir))
        assert result.valid is False
        assert any("Use when" in e for e in result.errors)

    def test_get_eval_script_path(self, kernel_path):
        """测试获取 eval 脚本路径。"""
        from app.kernel.skill_creator_impl import SkillCreatorKernelImpl

        impl = SkillCreatorKernelImpl(kernel_path)
        script_path = impl.get_eval_script_path()
        assert script_path.endswith("eval_description.py")
        assert os.path.isfile(script_path)

    def test_get_quality_checklist(self, kernel_path):
        """测试获取质量检查清单。"""
        from app.kernel.skill_creator_impl import SkillCreatorKernelImpl

        impl = SkillCreatorKernelImpl(kernel_path)
        checklist = impl.get_quality_checklist()
        assert len(checklist) > 0
        # 必须包含核心检查项
        item_ids = [item.item_id for item in checklist]
        assert "name_format" in item_ids
        assert "desc_use_when" in item_ids


class TestKernelRegistry:
    """KernelRegistry 单元测试。"""

    def test_singleton(self):
        """测试 KernelRegistry 是单例。"""
        from app.kernel.registry import KernelRegistry

        r1 = KernelRegistry.get_instance()
        r2 = KernelRegistry.get_instance()
        assert r1 is r2

    def test_get_kernel_not_found(self):
        """测试获取不存在的内核时抛出 KernelNotFoundError。"""
        from app.exceptions import KernelNotFoundError
        from app.kernel.registry import KernelRegistry

        registry = KernelRegistry.get_instance()
        with pytest.raises(KernelNotFoundError):
            registry.get_kernel("nonexistent-kernel-xyz")
