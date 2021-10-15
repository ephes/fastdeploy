from passlib.context import CryptContext


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(plain):
    return pwd_context.hash(plain)


def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)
