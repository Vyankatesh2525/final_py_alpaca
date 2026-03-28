# auth_schemas.py - Pydantic schemas for authentication requests and responses in Clau Trading Backend.
from pydantic import BaseModel

class LoginRequest(BaseModel):
    username: str
    password: str

class SignupRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    user_id: int
    message: str

class SignupResponse(BaseModel):
    message: str