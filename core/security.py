"""Embedding protection. Face embeddings can be inverted into face images (review finding 4),
so they are encrypted at rest with a Fernet (AES-128-CBC + HMAC) key kept outside the database."""
import numpy as np
from cryptography.fernet import Fernet
import config


def _key():
    if config.KEY_PATH.exists():
        return config.KEY_PATH.read_bytes()
    k = Fernet.generate_key()
    config.KEY_PATH.write_bytes(k)
    return k


_f = Fernet(_key())


def encrypt_embedding(vec: np.ndarray) -> bytes:
    return _f.encrypt(np.asarray(vec, dtype=np.float32).tobytes())


def decrypt_embedding(blob: bytes) -> np.ndarray:
    return np.frombuffer(_f.decrypt(blob), dtype=np.float32).copy()
