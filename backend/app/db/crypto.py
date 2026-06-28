"""
crypto.py — Database encryption utilities.

Transparently encrypts sensitive fields at rest (e.g. RTSP URLs, passwords)
using Fernet symmetric encryption.
"""

from cryptography.fernet import Fernet
from sqlalchemy.types import TypeDecorator, String

from app.core.config import get_settings

settings = get_settings()
_fernet = Fernet(settings.ENCRYPTION_KEY.encode())

class EncryptedString(TypeDecorator):
    """
    Transparently encrypts a string before saving to the database,
    and decrypts it upon retrieval.
    """
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _fernet.encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return _fernet.decrypt(value.encode()).decode()
        except Exception:
            # Fallback for plain-text data already in DB before encryption was added
            return value
