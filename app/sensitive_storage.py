import json

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def _cipher() -> Fernet:
    key = get_settings().data_encryption_key
    if not key:
        raise RuntimeError("Consented upload encryption is not configured")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("DATA_ENCRYPTION_KEY is not a valid Fernet key") from exc


def encrypt_image(image_bytes: bytes) -> bytes:
    return _cipher().encrypt(image_bytes)


def decrypt_image(encrypted_image: bytes) -> bytes:
    try:
        return _cipher().decrypt(encrypted_image)
    except InvalidToken as exc:
        raise RuntimeError("Stored image could not be decrypted") from exc


def encrypt_embedding(embedding: list[float]) -> bytes:
    payload = json.dumps(embedding, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return _cipher().encrypt(payload)


def decrypt_embedding(encrypted_embedding: bytes) -> list[float]:
    try:
        payload = _cipher().decrypt(encrypted_embedding)
        values = json.loads(payload)
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Stored embedding could not be decrypted") from exc
    if not isinstance(values, list) or not all(isinstance(value, (int, float)) for value in values):
        raise RuntimeError("Stored embedding has an invalid format")
    return [float(value) for value in values]
