"""
security.py — Password hashing and verification utilities.
Separated to avoid circular imports between database and auth.
"""

from passlib.context import CryptContext

# Using pbkdf2_sha256 instead of bcrypt to avoid the 72-char password limit
# and improve compatibility across different environments (like Windows).
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def hash_password(plain_password: str) -> str:
    """Hashes a plain-text password using bcrypt."""
    return pwd_context.hash(plain_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain-text password against a stored hash."""
    return pwd_context.verify(plain_password, hashed_password)
