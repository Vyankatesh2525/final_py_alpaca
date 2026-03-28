from cryptography.fernet import Fernet
from config import TOKEN_ENCRYPTION_KEY

_fernet = Fernet(TOKEN_ENCRYPTION_KEY.encode())

def encrypt_token(token: str) -> str:
    return _fernet.encrypt(token.encode()).decode()

def decrypt_token(encrypted: str) -> str:
    return _fernet.decrypt(encrypted.encode()).decode()
