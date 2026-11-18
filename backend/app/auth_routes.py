from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from .auth_dependencies import get_current_active_user
from .database import get_db
from .models import User
from .rate_limiter import limiter
from .services.auth_service import (
    AuthServiceError,
    InvalidCredentialsError,
    UserAlreadyExistsError,
    authenticate_user,
    create_access_token,
    create_guest_token,
    register_user,
    registration_enabled,
    serialize_user,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("3/hour")
def register(
    request: Request,
    payload: RegisterRequest,
    db: Session = Depends(get_db),
):
    if not registration_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El registro de usuarios está deshabilitado.",
        )
    try:
        user = register_user(db, str(payload.email), payload.password)
        return {
            "success": True,
            "message": "Cuenta creada correctamente.",
            "user": serialize_user(user),
        }
    except UserAlreadyExistsError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except AuthServiceError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/login")
@limiter.limit("5/minute")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    try:
        user = authenticate_user(
            db=db,
            email=form_data.username,
            password=form_data.password,
        )
        token, expires_in = create_access_token(user)
        return {
            "success": True,
            "access_token": token,
            "token_type": "bearer",
            "expires_in": expires_in,
            "user": serialize_user(user),
        }
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except AuthServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo iniciar sesión.",
        ) from error


@router.get("/me")
def get_my_profile(
    user: User = Depends(get_current_active_user),
):
    return {"success": True, "user": serialize_user(user)}


@router.post("/guest")
@limiter.limit("10/hour")
def create_guest_session(request: Request):
    """Crea una sesión temporal para visitantes sin registro."""
    try:
        token, expires_in, session_id = create_guest_token()

        return {
            "success": True,
            "access_token": token,
            "token_type": "bearer",
            "expires_in": expires_in,
            "guest_session_id": str(session_id),
            "is_guest": True,
        }

    except AuthServiceError as error:
        raise HTTPException(
            status_code=500,
            detail="No se pudo crear la sesión de invitado.",
        ) from error
