# auth_schemas.py - Pydantic schemas for authentication requests and responses.
from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    username: str
    password: str


class SignupRequest(BaseModel):
    username: str
    full_name: str = ""
    email: str
    phone_number: str = ""
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: int
    is_admin: bool = False
    message: str


class SignupResponse(BaseModel):
    message: str
    status: str
    token: str = ""


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    access_token: str
    message: str


class ForgotPasswordRequest(BaseModel):
    username: str   # accepts username or email


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class UserInfoResponse(BaseModel):
    username: str
    full_name: str
    email: str
    phone_number: str
