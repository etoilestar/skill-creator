"""
backend/app/kernel/skill_creator_impl.py

skill-creator 内核适配器具体实现。

职责：
    - 实现 KernelAdapter 接口，封装对 backend/kernels/skill-creator/ 目录的所有访问
    - 加载并解析 SKILL.md，提取创建指南和质量检查清单
    - 实现 Skill 目录结构校验逻辑（基于 OpenClaw 规范）
    - 提供 eval 脚本路径，供沙盒测试使用

重要约束：
    - 本类是唯一允许直接访问 backend/kernels/skill-creator/ 目录的代码
    - 其他所有服务必须通过 KernelAdapter 接口间接访问内核内容
    - 内核目录应以只读方式挂载，本类不应向内核目录写入任何内容
"""

import ast
import os
import re
from pathlib import Path
from typing import List

from ..exceptions import KernelNotLoadedError, KernelValidationError
from .base import ChecklistItem, KernelAdapter, KernelMeta, ValidationResult


class SkillCreatorKernelImpl(KernelAdapter):
    """
    skill-creator 内核适配器具体实现类。

    在系统启动时由 KernelLoader 实例化，通过 KernelRegistry 注册。
    实例化后会立即加载并缓存 SKILL.md 内容。

    Attributes:
        kernel_path: 内核目录的绝对路径（backend/kernels/skill-creator/）
        _skill_md_content: 缓存的 SKILL.md 全文内容
        _kernel_meta: 缓存的内核元数据
    """

    def __init__(self, kernel_path: str):
        """
        初始化内核适配器，加载并验证内核目录。

        Args:
            kernel_path: 内核目录的绝对路径

        Raises:
            KernelNotLoadedError: 当内核目录不存在或 SKILL.md 不存在时
        """
        self.kernel_path = Path(kernel_path).resolve()
        self._skill_md_content: str = ""
        self._kernel_meta: KernelMeta = None

        # 加载时立即校验和缓存内容
        self._load()

    def _load(self) -> None:
        """
        加载内核目录中的核心文件，校验完整性并缓存内容。

        加载顺序：
        1. 校验内核目录存在
        2. 校验 SKILL.md 存在
        3. 读取并缓存 SKILL.md 内容
        4. 读取 kernel.json 元数据（如存在）
        5. 校验 eval 脚本存在

        Raises:
            KernelNotLoadedError: 当必要文件缺失时
        """
        if not self.kernel_path.is_dir():
            raise KernelNotLoadedError(
                f"内核目录不存在: {self.kernel_path}，"
                "请运行 backend/scripts/download_kernel.py 下载内核"
            )

        skill_md_path = self.kernel_path / "SKILL.md"
        if not skill_md_path.is_file():
            raise KernelNotLoadedError(
                f"内核 SKILL.md 不存在: {skill_md_path}"
            )

        # 读取并缓存 SKILL.md 内容
        self._skill_md_content = skill_md_path.read_text(encoding="utf-8")

        # 读取 kernel.json 元数据
        kernel_json_path = self.kernel_path / "kernel.json"
        if kernel_json_path.is_file():
            import json
            meta_data = json.loads(kernel_json_path.read_text(encoding="utf-8"))
            self._kernel_meta = KernelMeta(
                kernel_id=meta_data.get("kernel_id", "skill-creator"),
                version=meta_data.get("version", "1.0.0"),
                source_url=meta_data.get("source_url", ""),
                description=meta_data.get("description", ""),
                capabilities=meta_data.get("capabilities", []),
                status=meta_data.get("status", "active"),
            )
        else:
            # kernel.json 不存在时使用默认元数据
            self._kernel_meta = KernelMeta(
                kernel_id="skill-creator",
                version="1.0.0",
                source_url="https://skillsmp.com/skills/openclaw-openclaw-skills-skill-creator-skill-md",
                description="OpenClaw Skill Creator 内核",
            )

        # 校验 eval 脚本存在
        eval_script = self.kernel_path / "scripts" / "eval_description.py"
        if not eval_script.is_file():
            # 警告而不报错，eval 脚本不存在时沙盒测试功能降级
            import warnings
            warnings.warn(
                f"内核 eval 脚本不存在: {eval_script}，沙盒测试功能将不可用",
                RuntimeWarning,
                stacklevel=2,
            )

    def get_kernel_meta(self) -> KernelMeta:
        """
        获取内核元数据。

        Returns:
            KernelMeta 对象。
        """
        return self._kernel_meta

    def get_skill_creation_guide(self) -> str:
        """
        获取 SKILL.md 全文内容，作为 AI Prompt 的核心指南注入。

        Returns:
            SKILL.md 全文字符串。

        Raises:
            KernelNotLoadedError: 当内容为空（加载失败）时
        """
        if not self._skill_md_content:
            raise KernelNotLoadedError("skill-creator 内核内容为空，请重新加载")
        return self._skill_md_content

    def get_skill_creation_guide_summary(self) -> str:
        """
        获取 SKILL.md 的摘要版本（前 60 行或第一个 ## 章节前的内容）。

        用于需求采集阶段的 System Prompt 注入，减少 Token 消耗。
        完整指南仅在 AI 主动请求（[FETCH_GUIDE]）时注入。

        Returns:
            SKILL.md 摘要字符串。
        """
        if not self._skill_md_content:
            return "（skill-creator 指南暂不可用）"
        lines = self._skill_md_content.splitlines()
        # 取前 60 行，或第一个 "## " 章节标题之前的内容（以较短者为准）
        cutoff = 60
        for i, line in enumerate(lines):
            if i > 0 and line.startswith("## ") and i < cutoff:
                cutoff = i
                break
        return "\n".join(lines[:cutoff])

    def get_skill_creation_guide_section(self, section: str) -> str:
        """
        获取 SKILL.md 中指定标题的章节内容。

        按 "## <section>" 标题切片，返回该标题到下一个同级标题（## 级别）之间的内容。
        匹配不区分大小写，section 参数支持关键词匹配（如 "phase1" 匹配 "## Phase 1: ..."）。

        Args:
            section: 章节关键词，如 "phase1" / "phase2" / "references" / "checklist"

        Returns:
            对应章节的 Markdown 文本；未找到时返回空字符串。
        """
        if not self._skill_md_content:
            return ""

        lines = self._skill_md_content.splitlines()
        section_lower = section.lower().replace("-", "").replace("_", "").replace(" ", "")

        start_idx = None
        end_idx = len(lines)

        for i, line in enumerate(lines):
            if line.startswith("## "):
                heading = line[3:].lower().replace("-", "").replace("_", "").replace(" ", "")
                if start_idx is None:
                    # 检查是否匹配目标章节（允许关键词部分匹配）
                    if section_lower in heading or heading.startswith(section_lower[:6]):
                        start_idx = i
                else:
                    # 找到下一个同级标题，结束截取
                    end_idx = i
                    break

        if start_idx is None:
            return ""

        return "\n".join(lines[start_idx:end_idx])

    def get_creation_prompt_template(self) -> str:
        """
        返回构建 Skill 创建 AI Prompt 的模板字符串。

        模板使用 Python str.format() 风格的占位符：
        - {skill_creation_guide}: 将被替换为 SKILL.md 全文
        - {requirement_spec_json}: 将被替换为用户的结构化需求 JSON
        - {skill_name}: 将被替换为目标 Skill 名称

        Returns:
            Prompt 模板字符串。
        """
        return """你是一个专业的 OpenClaw Skill 创建助手。

以下是 skill-creator 的完整创建指南，你必须严格遵循其中定义的规范和流程：

=== skill-creator 创建指南 ===
{skill_creation_guide}
=== 创建指南结束 ===

现在，请根据以下结构化需求，创建一个符合 OpenClaw Skill 规范的完整 SKILL.md 文件。

目标 Skill 名称：{skill_name}

结构化需求：
{requirement_spec_json}

输出要求：
1. 只输出 SKILL.md 的完整内容，不要输出其他任何内容
2. 严格按照 SKILL.md 格式规范（frontmatter + body）
3. description 字段必须包含 "Use when" 和 "NOT for" 结构
4. body 不超过 300 行
5. 使用中文编写 body 内容（如果需求是中文场景的话）

请直接输出 SKILL.md 内容："""

    def validate_skill_structure(self, skill_path: str) -> ValidationResult:
        """
        校验 Skill 目录结构是否符合 OpenClaw 规范。

        校验规则来源于 skill-creator SKILL.md 中的 "Skill Quality Checklist"：
        1. SKILL.md 必须存在
        2. frontmatter 必须包含 name 和 description
        3. name 必须是 lowercase kebab-case，不超过 64 个字符
        4. description 必须包含 "Use when"
        5. description 应包含 "NOT for"（警告而非错误）
        6. body 不超过 300 行
        7. scripts/ 中的 Python 文件语法正确（如存在）

        Args:
            skill_path: Skill 目录的绝对路径

        Returns:
            ValidationResult 对象。
        """
        errors = []
        warnings = []
        path = Path(skill_path)

        # 校验 1：目录存在
        if not path.is_dir():
            return ValidationResult(valid=False, errors=[f"Skill 目录不存在: {skill_path}"])

        # 校验 2：SKILL.md 存在
        skill_md = path / "SKILL.md"
        if not skill_md.is_file():
            return ValidationResult(valid=False, errors=["SKILL.md 文件不存在"])

        # 解析 SKILL.md
        content = skill_md.read_text(encoding="utf-8")
        lines = content.splitlines()
        frontmatter = self._parse_frontmatter(content)

        # 校验 3：frontmatter 字段
        name = frontmatter.get("name", "")
        description = frontmatter.get("description", "")

        if not name:
            errors.append("SKILL.md frontmatter 缺少 name 字段")
        elif not re.match(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$|^[a-z0-9]$", name):
            errors.append(f"name 字段 '{name}' 不符合 lowercase kebab-case 规范")
        elif len(name) > 64:
            errors.append(f"name 字段长度超过 64 个字符: {len(name)}")

        if not description:
            errors.append("SKILL.md frontmatter 缺少 description 字段")
        else:
            # 校验 description 结构
            if "Use when" not in description and "use when" not in description.lower():
                errors.append("description 缺少 'Use when' 触发场景说明")
            if "NOT for" not in description and "not for" not in description.lower():
                warnings.append("description 建议添加 'NOT for' 反例说明，以防止误触发")

        # 校验 4：body 行数
        body_lines = len(lines)
        if body_lines > 300:
            warnings.append(
                f"SKILL.md 共 {body_lines} 行，建议保持在 300 行以内，"
                "超长内容建议移至 references/ 目录"
            )

        # 校验 5：scripts/ 中的 Python 语法（如存在）
        scripts_dir = path / "scripts"
        if scripts_dir.is_dir():
            for py_file in scripts_dir.glob("*.py"):
                try:
                    ast.parse(py_file.read_text(encoding="utf-8"))
                except SyntaxError as e:
                    errors.append(
                        f"scripts/{py_file.name} 语法错误: 第 {e.lineno} 行 - {e.msg}"
                    )

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def get_quality_checklist(self) -> List[ChecklistItem]:
        """
        返回 Skill 质量检查清单。

        清单来源于 skill-creator SKILL.md 中的 "Skill Quality Checklist"。

        Returns:
            ChecklistItem 列表。
        """
        return [
            ChecklistItem(
                item_id="name_format",
                description="name 字段为 lowercase kebab-case，不超过 64 个字符",
            ),
            ChecklistItem(
                item_id="desc_use_when",
                description="description 包含 'Use when' 和具体触发场景",
            ),
            ChecklistItem(
                item_id="desc_not_for",
                description="description 包含 'NOT for' 以防止误触发",
            ),
            ChecklistItem(
                item_id="body_length",
                description="SKILL.md body 不超过 300 行",
            ),
            ChecklistItem(
                item_id="no_aux_docs",
                description="无 README、CHANGELOG 等辅助文档（保持 Skill 精简）",
            ),
            ChecklistItem(
                item_id="scripts_tested",
                description="scripts/ 中的脚本语法正确且可运行",
            ),
            ChecklistItem(
                item_id="references_linked",
                description="references/ 文件已在 SKILL.md 中链接并说明使用场景",
            ),
        ]

    def get_eval_script_path(self) -> str:
        """
        返回 eval_description.py 的绝对路径。

        Returns:
            脚本文件绝对路径字符串。

        Raises:
            KernelNotLoadedError: 当脚本文件不存在时
        """
        script_path = self.kernel_path / "scripts" / "eval_description.py"
        if not script_path.is_file():
            raise KernelNotLoadedError(
                f"eval 脚本不存在: {script_path}，沙盒测试功能不可用"
            )
        return str(script_path)

    @staticmethod
    def _parse_frontmatter(content: str) -> dict:
        """
        解析 SKILL.md 的 YAML frontmatter，提取 name 和 description。

        Args:
            content: SKILL.md 全文字符串

        Returns:
            包含 name 和 description 的字典（字段不存在时对应值为空字符串）
        """
        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            return {"name": "", "description": ""}

        try:
            end = lines.index("---", 1)
        except ValueError:
            return {"name": "", "description": ""}

        name, description = "", ""
        for line in lines[1:end]:
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("description:"):
                description = line.split(":", 1)[1].strip()

        return {"name": name, "description": description}
