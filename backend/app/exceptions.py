"""
backend/app/exceptions.py

应用自定义异常类定义。

职责：
    - 为各业务场景定义语义明确的异常类型
    - 统一异常的 HTTP 状态码映射
    - 配合全局错误处理器（error handler）生成标准 JSON 错误响应

异常层次结构：
    AppBaseError（所有应用异常的基类）
    ├── KernelError（内核相关异常）
    │   ├── KernelNotFoundError
    │   ├── KernelNotLoadedError
    │   └── KernelValidationError
    ├── ModelProviderError（AI 模型调用相关异常）
    │   ├── ModelNotConfiguredError
    │   ├── ModelConnectionError
    │   └── ModelCallError
    ├── FileServiceError（文件操作相关异常）
    │   ├── PathSecurityError      ← 路径安全违规，最高优先级
    │   ├── FileNotFoundError
    │   └── FileWriteError
    ├── SkillCreationError（Skill 创建相关异常）
    │   ├── RequirementIncompleteError
    │   ├── SkillGenerationError
    │   └── SkillValidationError
    └── SandboxError（沙盒测试相关异常）
        ├── SandboxTimeoutError
        └── SandboxExecutionError

注意：
    - 所有业务异常都应继承 AppBaseError，以确保能被统一错误处理器捕获
    - PathSecurityError 必须返回 400（不允许泄露服务器路径信息）
"""


class AppBaseError(Exception):
    """
    应用异常基类。

    Attributes:
        code: 机器可读的错误代码（如 "KERNEL_NOT_FOUND"）
        message: 人类可读的中文错误描述
        http_status: 对应的 HTTP 状态码
    """

    code: str = "APP_ERROR"
    message: str = "应用错误"
    http_status: int = 500

    def __init__(self, message: str = None, code: str = None):
        if message:
            self.message = message
        if code:
            self.code = code
        super().__init__(self.message)


# ------------------------------------------------------------------
# 内核相关异常
# ------------------------------------------------------------------


class KernelError(AppBaseError):
    """内核操作相关异常基类。"""

    code = "KERNEL_ERROR"
    message = "内核操作失败"
    http_status = 500


class KernelNotFoundError(KernelError):
    """指定的内核 ID 未注册。"""

    code = "KERNEL_NOT_FOUND"
    message = "内核不存在"
    http_status = 404


class KernelNotLoadedError(KernelError):
    """内核目录存在但加载失败（文件损坏、checksum 不匹配等）。"""

    code = "KERNEL_NOT_LOADED"
    message = "内核未能成功加载"
    http_status = 500


class KernelValidationError(KernelError):
    """内核文件校验失败（SKILL.md 格式不正确等）。"""

    code = "KERNEL_VALIDATION_ERROR"
    message = "内核文件校验失败"
    http_status = 500


# ------------------------------------------------------------------
# AI 模型调用相关异常
# ------------------------------------------------------------------


class ModelProviderError(AppBaseError):
    """AI 模型调用相关异常基类。"""

    code = "MODEL_PROVIDER_ERROR"
    message = "模型调用失败"
    http_status = 500


class ModelNotConfiguredError(ModelProviderError):
    """当前没有激活的模型配置。"""

    code = "MODEL_NOT_CONFIGURED"
    message = "当前没有已激活的模型配置，请先在设置中添加并激活模型"
    http_status = 400


class ModelConnectionError(ModelProviderError):
    """模型 API 连通性测试失败。"""

    code = "MODEL_CONNECTION_ERROR"
    message = "无法连接到模型 API"
    http_status = 503


class ModelCallError(ModelProviderError):
    """模型 API 调用时发生错误（超时、鉴权失败、返回格式异常等）。"""

    code = "MODEL_CALL_ERROR"
    message = "模型 API 调用失败"
    http_status = 500


# ------------------------------------------------------------------
# 文件操作相关异常
# ------------------------------------------------------------------


class FileServiceError(AppBaseError):
    """文件操作相关异常基类。"""

    code = "FILE_SERVICE_ERROR"
    message = "文件操作失败"
    http_status = 500


class PathSecurityError(FileServiceError):
    """
    路径安全违规异常。

    当请求的文件路径超出允许的工作区边界时抛出（路径遍历攻击防护）。
    返回 400 而非 403，避免泄露路径边界信息。
    """

    code = "PATH_SECURITY_VIOLATION"
    message = "非法路径访问，操作被拒绝"
    http_status = 400


class WorkspaceFileNotFoundError(FileServiceError):
    """工作区中指定文件不存在。"""

    code = "FILE_NOT_FOUND"
    message = "文件不存在"
    http_status = 404


class FileWriteError(FileServiceError):
    """文件写入失败。"""

    code = "FILE_WRITE_ERROR"
    message = "文件写入失败"
    http_status = 500


# ------------------------------------------------------------------
# Skill 创建相关异常
# ------------------------------------------------------------------


class SkillCreationError(AppBaseError):
    """Skill 创建流程相关异常基类。"""

    code = "SKILL_CREATION_ERROR"
    message = "Skill 创建失败"
    http_status = 500


class RequirementIncompleteError(SkillCreationError):
    """需求完整度不足，无法触发创建流程。"""

    code = "REQUIREMENT_INCOMPLETE"
    message = "需求信息不完整，请继续补充需求后再创建"
    http_status = 400


class SkillGenerationError(SkillCreationError):
    """AI 生成 SKILL.md 内容失败或内容不符合规范。"""

    code = "SKILL_GENERATION_ERROR"
    message = "Skill 内容生成失败"
    http_status = 500


class SkillValidationError(SkillCreationError):
    """生成的 Skill 未通过结构校验。"""

    code = "SKILL_VALIDATION_ERROR"
    message = "生成的 Skill 结构校验失败"
    http_status = 422


# ------------------------------------------------------------------
# 沙盒测试相关异常
# ------------------------------------------------------------------


class SandboxError(AppBaseError):
    """沙盒测试相关异常基类。"""

    code = "SANDBOX_ERROR"
    message = "沙盒测试失败"
    http_status = 500


class SandboxTimeoutError(SandboxError):
    """沙盒执行超时。"""

    code = "SANDBOX_TIMEOUT"
    message = "沙盒测试执行超时"
    http_status = 504


class SandboxExecutionError(SandboxError):
    """沙盒容器执行异常（非测试失败，而是执行环境本身的错误）。"""

    code = "SANDBOX_EXECUTION_ERROR"
    message = "沙盒执行环境异常"
    http_status = 500


# ------------------------------------------------------------------
# 任务相关异常
# ------------------------------------------------------------------


class TaskNotFoundError(AppBaseError):
    """指定的任务 ID 不存在。"""

    code = "TASK_NOT_FOUND"
    message = "任务不存在"
    http_status = 404


class InvalidTaskStateError(AppBaseError):
    """当前任务状态不允许此操作（如对已完成的任务触发创建）。"""

    code = "INVALID_TASK_STATE"
    message = "当前任务状态不允许此操作"
    http_status = 409


# ------------------------------------------------------------------
# 会话相关异常
# ------------------------------------------------------------------


class SessionNotFoundError(AppBaseError):
    """指定的会话 ID 不存在。"""

    code = "SESSION_NOT_FOUND"
    message = "会话不存在"
    http_status = 404
