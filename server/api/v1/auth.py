from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from storage.supabase import get_anon_client

router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


@router.post("/login", response_model=LoginResponse, summary="User login")
async def login(body: LoginRequest):
    """
    Authenticate with email and password via Supabase Auth.
    Returns a JWT access token.
    """
    client = get_anon_client()
    try:
        response = client.auth.sign_in_with_password(
            {"email": body.email, "password": body.password}
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        ) from exc

    if not response.session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed.",
        )

    return LoginResponse(
        access_token=response.session.access_token,
        user_id=str(response.user.id),
        email=response.user.email,
    )
