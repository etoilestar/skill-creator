"""
backend/app/model/encryption.py

API Key 加密与解密工具函数。

职责：
    - 提供 API Key 的 Fernet 对称加密存储能力
    - 确保数据库中的 API Key 以密文形式存储，防止数据库泄露时密钥外露
    - 加密密钥从环境变量 ENCRYPTION_KEY 读取

安全注意事项：
    - ENCRYPTION_KEY 本身必须通过 Docker Secret 或环境变量注入，不能提交到代码仓库
    - 开发环境使用占位密钥，生产环境必须更换为强随机密钥
    - Fernet 使用 AES-128-CBC + HMAC-SHA256，密钥 32 字节，安全强度足够

生成密钥的方法：
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    print(key.decode())
"""

import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from ..exceptions import AppBaseError


class EncryptionError(AppBaseError):
    """加密/解密操作异常。"""
    code = "ENCRYPTION_ERROR"
    message = "密钥加密/解密失败"
    http_status = 500


def _get_fernet() -> Fernet:
    """
    获取 Fernet 加密实例（使用环境变量中的密钥）。

    Returns:
        配置好的 Fernet 实例。

    Raises:
        EncryptionError: 当 ENCRYPTION_KEY 格式不正确时
    """
    key = os.environ.get("ENCRYPTION_KEY", "")
    if not key:
        # 开发环境回退到固定密钥（仅用于开发，生产必须设置环境变量）
        key = "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTI="

    try:
        # 确保密钥为 bytes 类型
        if isinstance(key, str):
            key = key.encode()
        return Fernet(key)
    except Exception as e:
        raise EncryptionError(f"ENCRYPTION_KEY 格式无效: {e}") from e


def encrypt_api_key(plaintext: str) -> Optional[str]:
    """
    加密 API Key 明文，返回 Fernet 密文字符串。

    Args:
        plaintext: API Key 明文字符串

    Returns:
        加密后的密文字符串（str 类型，可直接存入数据库）。
        如果 plaintext 为空，返回 None。
    """
    if not plaintext:
        return None
    fernet = _get_fernet()
    encrypted = fernet.encrypt(plaintext.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_api_key(ciphertext: str) -> str:
    """
    解密存储的 API Key 密文，返回明文字符串。

    Args:
        ciphertext: 数据库中存储的加密密文字符串

    Returns:
        解密后的 API Key 明文字符串。
        如果 ciphertext 为空，返回空字符串。

    Raises:
        EncryptionError: 当密文无效（被篡改或密钥错误）时
    """
    if not ciphertext:
        return ""
    try:
        fernet = _get_fernet()
        decrypted = fernet.decrypt(ciphertext.encode("utf-8"))
        return decrypted.decode("utf-8")
    except InvalidToken as e:
        raise EncryptionError(
            "API Key 解密失败，可能是密钥不匹配或数据被篡改。"
            "如果更换了 ENCRYPTION_KEY，需要重新配置模型参数。"
        ) from e
