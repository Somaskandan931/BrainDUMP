"""schemas/auth.py — request/response models for /api/auth/*."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    id_token: str


class GithubLoginRequest(BaseModel):
    code: str


class UserOut(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    google_picture_url: Optional[str] = None
    github_avatar_url: Optional[str] = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
