from cryptography.fernet import Fernet

from app.core.config import settings


def _get_fernet(fernet_key: str | None = None) -> Fernet:
    """根据指定密钥或全局配置构造 Fernet 实例。"""
    raw_key = fernet_key if fernet_key is not None else settings.FERNET_KEY
    if not raw_key or not raw_key.strip():
        raise ValueError("FERNET_KEY 未配置，无法执行敏感数据加解密")
    return Fernet(raw_key.strip().encode("utf-8"))


def encrypt_secret(plaintext: str, fernet_key: str | None = None) -> str:
    """使用 Fernet 对称加密敏感字符串（如代理密码、2FA 密码）。"""
    fernet = _get_fernet(fernet_key)
    token = fernet.encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(ciphertext: str, fernet_key: str | None = None) -> str:
    """使用 Fernet 解密敏感字符串。"""
    fernet = _get_fernet(fernet_key)
    plaintext = fernet.decrypt(ciphertext.encode("utf-8"))
    return plaintext.decode("utf-8")

