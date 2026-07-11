"""
Password hashing helpers used by the auth router.
"""
import bcrypt

MAX_BCRYPT_BYTES = 72


def hash_password(plain_password: str) -> str:
    pw_bytes = plain_password.encode("utf-8")[:MAX_BCRYPT_BYTES]
    hashed = bcrypt.hashpw(pw_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        pw_bytes = plain_password.encode("utf-8")[:MAX_BCRYPT_BYTES]
        return bcrypt.checkpw(pw_bytes, password_hash.encode("utf-8"))
    except Exception:
        return False