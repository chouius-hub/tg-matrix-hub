import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet, InvalidToken

# 确保从仓库根目录或 backend 目录执行 pytest 都能找到 app 模块
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.security import decrypt_secret, encrypt_secret  # noqa: E402


def test_encrypt_and_decrypt_roundtrip() -> None:
    """验证正常明文经过 Fernet 加密与解密后能完整还原。"""
    key = Fernet.generate_key().decode("utf-8")
    secret_text = "p@ssw0rd_proxy_2fa_!#$"

    ciphertext = encrypt_secret(secret_text, fernet_key=key)
    assert ciphertext != secret_text
    assert decrypt_secret(ciphertext, fernet_key=key) == secret_text


def test_encrypt_produces_distinct_ciphertexts() -> None:
    """验证 Fernet 每次加密同一明文会生成不同密文（包含随机 IV）。"""
    key = Fernet.generate_key().decode("utf-8")
    secret_text = "same_secret"

    c1 = encrypt_secret(secret_text, fernet_key=key)
    c2 = encrypt_secret(secret_text, fernet_key=key)
    assert c1 != c2


def test_decrypt_with_wrong_key_raises() -> None:
    """验证使用错误密钥解密时抛出 InvalidToken 异常。"""
    key_1 = Fernet.generate_key().decode("utf-8")
    key_2 = Fernet.generate_key().decode("utf-8")

    ciphertext = encrypt_secret("my_2fa_password", fernet_key=key_1)
    with pytest.raises(InvalidToken):
        decrypt_secret(ciphertext, fernet_key=key_2)


def test_empty_key_raises_value_error() -> None:
    """验证未提供有效 FERNET_KEY 时拒绝加解密并抛出 ValueError。"""
    with pytest.raises(ValueError):
        encrypt_secret("secret", fernet_key="")

