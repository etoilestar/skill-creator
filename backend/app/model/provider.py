"""
backend/app/model/provider.py

AI 模型接入层 —— ModelProvider 抽象类与工厂函数。

职责：
    - 定义统一的 AI 模型调用接口
    - 通过工厂函数根据配置动态构建具体 Provider 实例
    - 封装模型调用重试逻辑（使用 tenacity 指数退避）
    - 提供连通性测试接口，用于保存配置前验证

支持的 Provider 类型：
    - openai: 调用 OpenAI 官方 API（api.openai.com）
    - azure: 调用 Azure OpenAI Service
    - local_openai_compat: 调用兼容 OpenAI 接口的本地模型（Ollama / vLLM 等）

扩展方向：
    - 后续可添加 AnthropicProvider、QwenProvider 等专用实现
    - 支持流式输出（stream_chat）用于前端实时显示 AI 响应

注意：
    - ModelProvider 不直接访问数据库，所需配置由调用方传入
    - API Key 解密后传入，本层不处理加密逻辑
"""

from dataclasses import dataclass
from typing import Generator, List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from ..exceptions import ModelCallError, ModelConnectionError, ModelNotConfiguredError


@dataclass
class Message:
    """
    对话消息数据类。

    Attributes:
        role: 消息角色（"system" / "user" / "assistant"）
        content: 消息内容
    """

    role: str
    content: str

    def to_dict(self) -> dict:
        """转换为 OpenAI API 消息格式字典。"""
        return {"role": self.role, "content": self.content}


@dataclass
class ConnectionTestResult:
    """
    模型连通性测试结果。

    Attributes:
        success: 是否连通成功
        latency_ms: 响应延迟（毫秒），失败时为 None
        error: 错误信息，成功时为 None
        model_info: 模型返回的附加信息（如模型名称、版本）
    """

    success: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    model_info: Optional[dict] = None


class OpenAICompatProvider:
    """
    兼容 OpenAI 接口的模型 Provider 实现。

    覆盖以下场景：
    - OpenAI 官方 API（api_base_url 为空或默认值）
    - Azure OpenAI Service（需要特殊的 api_base_url 格式）
    - 本地 Ollama 服务（http://ollama:11434/v1）
    - 本地 vLLM 服务
    - 兼容 OpenAI 接口的其他服务（如 DeepSeek、Moonshot 等）

    Attributes:
        api_key: 解密后的 API Key
        api_base_url: API 基础 URL（None 时使用 OpenAI 默认值）
        model_name: 模型名称
        max_tokens: 最大 Token 数
        temperature: 温度参数
        extra_params: 额外模型参数
    """

    def __init__(
        self,
        api_key: str,
        model_name: str,
        api_base_url: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        extra_params: Optional[dict] = None,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.api_base_url = api_base_url
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.extra_params = extra_params or {}

        # 懒加载 OpenAI 客户端（避免导入时报错）
        self._client = None

    def _get_client(self):
        """
        获取或创建 OpenAI 客户端实例。

        使用懒加载模式，避免在模块导入时就初始化客户端。
        如果 api_base_url 为空，使用 OpenAI 官方默认地址。

        Returns:
            openai.OpenAI 客户端实例。
        """
        if self._client is None:
            import openai
            kwargs = {
                "api_key": self.api_key or "not-needed",  # 本地模型可能不需要 Key
            }
            if self.api_base_url:
                kwargs["base_url"] = self.api_base_url
            self._client = openai.OpenAI(**kwargs)
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def chat(self, messages: List[Message], system: Optional[str] = None) -> str:
        """
        调用模型进行对话，返回完整响应文本。

        使用 tenacity 实现指数退避重试（最多 3 次，间隔 2-30 秒）。
        重试策略：网络超时、5xx 错误重试；4xx 错误（如鉴权失败）不重试。

        Args:
            messages: 对话历史消息列表
            system: 可选的 system 提示词（会被插入到消息列表最前面）

        Returns:
            模型返回的文本内容字符串。

        Raises:
            ModelCallError: 当 API 调用失败时（包含详细错误信息）
        """
        try:
            client = self._get_client()

            # 构建消息列表：system 消息放最前面
            api_messages = []
            if system:
                api_messages.append({"role": "system", "content": system})
            api_messages.extend([m.to_dict() for m in messages])

            # 合并额外参数
            call_kwargs = {
                "model": self.model_name,
                "messages": api_messages,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                **self.extra_params,
            }

            response = client.chat.completions.create(**call_kwargs)
            return response.choices[0].message.content or ""

        except Exception as e:
            # 将所有异常包装为 ModelCallError，避免上层代码依赖具体异常类型
            raise ModelCallError(
                f"模型 '{self.model_name}' 调用失败: {type(e).__name__}: {str(e)}"
            ) from e

    def stream_chat(
        self, messages: List[Message], system: Optional[str] = None
    ) -> "Generator[str, None, None]":
        """
        调用模型进行对话，以生成器方式逐块 yield 响应文本。

        与 chat() 不同，stream_chat 不使用 tenacity 重试，因为流式响应一旦开始
        就无法回滚。调用方应自行处理异常（捕获 ModelCallError）。

        Args:
            messages: 对话历史消息列表
            system: 可选的 system 提示词（会被插入到消息列表最前面）

        Yields:
            模型返回的文本内容分片（str），每次 yield 一小块

        Raises:
            ModelCallError: 当 API 调用初始化失败时（流建立前）
        """
        try:
            client = self._get_client()

            api_messages = []
            if system:
                api_messages.append({"role": "system", "content": system})
            api_messages.extend([m.to_dict() for m in messages])

            call_kwargs = {
                "model": self.model_name,
                "messages": api_messages,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "stream": True,
                **self.extra_params,
            }

            stream = client.chat.completions.create(**call_kwargs)
            for chunk in stream:
                delta_content = chunk.choices[0].delta.content if chunk.choices else None
                if delta_content:
                    yield delta_content

        except Exception as e:
            raise ModelCallError(
                f"模型 '{self.model_name}' 流式调用失败: {type(e).__name__}: {str(e)}"
            ) from e

    def test_connection(self) -> ConnectionTestResult:
        """
        测试模型 API 连通性。

        发送一条最简单的消息（"hi"）验证 API 可达性，
        记录响应延迟用于展示给用户。

        Returns:
            ConnectionTestResult 对象，包含成功状态、延迟和错误信息。
        """
        import time

        start = time.time()
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5,
            )
            latency_ms = (time.time() - start) * 1000
            return ConnectionTestResult(
                success=True,
                latency_ms=round(latency_ms, 1),
                model_info={"model": response.model},
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                error=str(e),
            )


class ModelProviderFactory:
    """
    模型 Provider 工厂类。

    根据模型配置信息动态构建对应的 Provider 实例。
    调用方不需要知道具体的 Provider 实现类。

    使用方式：
        config = ModelConfig.query.filter_by(is_active=True).first()
        provider = ModelProviderFactory.create(config, decrypted_key)
        response = provider.chat(messages)
    """

    @staticmethod
    def create(config, decrypted_api_key: str) -> OpenAICompatProvider:
        """
        根据 ModelConfig 创建对应的 Provider 实例。

        当前所有 Provider 类型都使用 OpenAI 兼容接口，
        后续可在此处根据 config.provider 字段分支创建不同实现。

        Args:
            config: ModelConfig 数据模型实例
            decrypted_api_key: 解密后的 API Key 明文

        Returns:
            配置好的 Provider 实例。

        Raises:
            ModelNotConfiguredError: 当 config 为 None 时
        """
        if config is None:
            raise ModelNotConfiguredError()

        return OpenAICompatProvider(
            api_key=decrypted_api_key,
            model_name=config.model_name,
            api_base_url=config.api_base_url,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            extra_params=config.extra_params or {},
        )

    @staticmethod
    def create_from_active_config() -> OpenAICompatProvider:
        """
        从数据库加载当前激活的模型配置并创建 Provider 实例。

        此方法需要在 Flask 应用上下文中调用（有数据库访问）。

        Returns:
            配置好的 Provider 实例。

        Raises:
            ModelNotConfiguredError: 当没有激活配置时
        """
        from ..models.model_config import ModelConfig
        from .encryption import decrypt_api_key

        config = ModelConfig.query.filter_by(is_active=True).first()
        if config is None:
            raise ModelNotConfiguredError()

        decrypted_key = decrypt_api_key(config.api_key_encrypted) if config.api_key_encrypted else ""
        return ModelProviderFactory.create(config, decrypted_key)
