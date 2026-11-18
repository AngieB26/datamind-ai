from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .services.auth_service import (
    decode_access_token,
    decode_guest_token,
)


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login"
)

optional_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login",
    auto_error=False,
)


@dataclass(frozen=True)
class AuthPrincipal:
    """Identidad autenticada: usuario registrado o visitante."""

    user: User | None = None
    guest_session_id: UUID | None = None

    @property
    def is_guest(self) -> bool:
        return self.guest_session_id is not None

    @property
    def is_registered(self) -> bool:
        return self.user is not None


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sesión inválida, ausente o expirada.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Valida exclusivamente tokens de usuarios registrados."""

    try:
        user_id = decode_access_token(token)
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise _unauthorized()

    user = db.get(User, user_id)

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El usuario no existe o está desactivado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_current_active_user(
    user: User = Depends(get_current_user),
) -> User:
    """Exige una cuenta registrada y activa."""

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta está desactivada.",
        )

    return user


def get_current_principal(
    token: str | None = Depends(optional_oauth2_scheme),
    db: Session = Depends(get_db),
) -> AuthPrincipal:
    """
    Reconoce una cuenta registrada o una sesión temporal de invitado.
    No permite solicitudes anónimas sin token.
    """

    if not token:
        raise _unauthorized()

    try:
        user_id = decode_access_token(token)

        user = db.get(User, user_id)

        if user is None or not user.is_active:
            raise _unauthorized()

        return AuthPrincipal(user=user)

    except jwt.InvalidTokenError:
        pass

    try:
        guest_session_id = decode_guest_token(token)
        return AuthPrincipal(
            guest_session_id=guest_session_id
        )
    except jwt.InvalidTokenError:
        raise _unauthorized()