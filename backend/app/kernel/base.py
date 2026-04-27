"""
backend/app/kernel/base.py

内核适配器抽象基类定义。

职责：
    - 定义所有 Skill 创建内核必须实现的统一接口
    - 外围业务层（Services）只依赖此接口，不依赖具体内核实现
    - 保证内核可以在不修改业务代码的前提下被替换或升级

接口设计原则：
    - get_skill_creation_guide(): 返回内核的创建指南（用于注入 AI System Prompt）
    - get_creation_prompt_template(): 返回构建 AI Prompt 的模板
    - validate_skill_structure(): 校验生成的 Skill 目录结构是否合规
    - get_quality_checklist(): 返回 Skill 质量检查清单
    - get_eval_script_path(): 返回触发精度测试脚本的绝对路径
    - get_kernel_meta(): 返回内核元数据（版本、来源等）

未来扩展点：
    - 可以实现 SkillCreatorV2KernelImpl 替换当前实现
    - 可以实现 SkillCreatorCNKernelImpl（中文增强版）
    - 可以实现 SkillCreatorFinanceKernelImpl（金融领域专业版）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class KernelMeta:
    """
    内核元数据。

    Attributes:
        kernel_id: 内核唯一标识符
        version: 内核版本号
        source_url: 内核来源 URL
        description: 内核功能描述
        capabilities: 内核支持的能力列表
        status: 内核状态（active / inactive）
    """

    kernel_id: str
    version: str
    source_url: str
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    status: str = "active"


@dataclass
class ValidationResult:
    """
    Skill 结构校验结果。

    Attributes:
        valid: 是否通过校验
        errors: 校验错误列表（每条是一个中文错误描述）
        warnings: 校验警告列表（不影响合规性，但建议改进）
    """

    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ChecklistItem:
    """
    Skill 质量检查清单项。

    Attributes:
        item_id: 检查项 ID
        description: 检查项描述（中文）
        passed: 是否通过（None 表示尚未检查）
        detail: 详细说明
    """

    item_id: str
    description: str
    passed: Optional[bool] = None
    detail: str = ""


class KernelAdapter(ABC):
    """
    Skill 创建内核适配器抽象基类。

    所有具体内核实现都必须继承此类并实现所有抽象方法。
    外围业务层（Services）只依赖此接口，不依赖具体实现类。

    这是整个系统中最重要的抽象边界：
        外围业务代码 ←→ KernelAdapter（接口）←→ 具体内核实现
    只要 KernelAdapter 接口不变，内核可以随时替换，
    而外围的 SessionService、SkillCreationService 等不需要任何修改。
    """

    @abstractmethod
    def get_kernel_meta(self) -> KernelMeta:
        """
        获取内核元数据。

        Returns:
            KernelMeta 对象，包含内核版本、来源、能力等信息。
        """
        ...

    @abstractmethod
    def get_skill_creation_guide(self) -> str:
        """
        获取 Skill 创建指南全文（即内核 SKILL.md 的全部内容）。

        此内容将作为 AI System Prompt 的核心组成部分，
        指导 AI 理解 OpenClaw Skill 的规范和创建流程。

        Returns:
            SKILL.md 全文字符串（Markdown 格式）。

        Raises:
            KernelNotLoadedError: 当内核未成功加载时
        """
        ...

    @abstractmethod
    def get_creation_prompt_template(self) -> str:
        """
        获取构建 Skill 创建 AI Prompt 的模板。

        模板中包含占位符，由 SkillCreationService 填入实际的需求数据。
        模板应引导 AI 按照 skill-creator 的创建流程生成标准格式的 SKILL.md。

        Returns:
            包含占位符的 Prompt 模板字符串。
        """
        ...

    @abstractmethod
    def validate_skill_structure(self, skill_path: str) -> ValidationResult:
        """
        校验指定路径的 Skill 目录结构是否符合 OpenClaw 规范。

        校验内容包括：
        - SKILL.md 文件是否存在
        - SKILL.md frontmatter 是否包含 name 和 description 字段
        - name 是否为 lowercase kebab-case
        - description 是否包含 "Use when" 和 "NOT for" 结构
        - 文件行数是否在 300 行以内
        - scripts/ 目录（如存在）中的 Python 文件语法是否正确

        Args:
            skill_path: Skill 目录的绝对路径

        Returns:
            ValidationResult 对象，包含是否通过和错误/警告列表。
        """
        ...

    @abstractmethod
    def get_quality_checklist(self) -> List[ChecklistItem]:
        """
        获取 Skill 质量检查清单。

        清单来源于 skill-creator SKILL.md 中定义的 "Skill Quality Checklist"。
        可用于向用户展示检查项状态，或作为 AI 生成 Skill 后的自检依据。

        Returns:
            ChecklistItem 列表，包含所有检查项的描述和检查逻辑。
        """
        ...

    @abstractmethod
    def get_eval_script_path(self) -> str:
        """
        获取触发精度评估脚本的绝对路径。

        此脚本（eval_description.py）将在沙盒容器中被调用，
        用于评估生成 Skill 的描述触发精度。

        Returns:
            eval_description.py 的绝对路径字符串。

        Raises:
            KernelNotLoadedError: 当脚本文件不存在时
        """
        ...
