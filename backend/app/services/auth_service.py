from __future__ import annotations

import os
from uuid import UUID, uuid4
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import User


load_dotenv()

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "datamind-ai"
password_hasher = PasswordHasher()


class AuthServiceError(RuntimeError):
    """Error al registrar o autenticar usuarios."""


class UserAlreadyExistsError(AuthServiceError):
    """El correo ya está registrado."""


class InvalidCredentialsError(AuthServiceError):
    """Las credenciales no son válidas."""


def get_jwt_secret() -> str:
    secret = os.getenv("AUTH_SECRET_KEY", "").strip()
    if len(secret) < 32:
        raise AuthServiceError("La clave JWT no está configurada correctamente.")
    return secret


def get_token_expiration() -> int:
    try:
        minutes = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "30"))
    except ValueError as error:
        raise AuthServiceError("La expiración JWT no es válida.") from error
    if minutes < 1 or minutes > 1440:
        raise AuthServiceError("La expiración JWT debe estar entre 1 y 1440 minutos.")
    return minutes


def registration_enabled() -> bool:
    return os.getenv("AUTH_ALLOW_REGISTRATION", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise AuthServiceError("La contraseña debe tener al menos 8 caracteres.")
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def serialize_user(user: User) -> dict[str, object]:
    return {
        "user_id": user.user_id,
        "email": user.email,
        "is_active": user.is_active,
        "created_at": user.created_at,
    }


def register_user(db: Session, email: str, password: str) -> User:
    normalized_email = normalize_email(email)
    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError as error:
        db.rollback()
        raise UserAlreadyExistsError(
            "Ya existe una cuenta con ese correo."
        ) from error
    except SQLAlchemyError as error:
        db.rollback()
        raise AuthServiceError("No se pudo registrar el usuario.") from error


def authenticate_user(db: Session, email: str, password: str) -> User:
    try:
        user = db.scalar(
            select(User).where(User.email == normalize_email(email))
        )
    except SQLAlchemyError as error:
        raise AuthServiceError("No se pudo consultar el usuario.") from error

    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("Correo o contraseña incorrectos.")
    if not user.is_active:
        raise InvalidCredentialsError("La cuenta está desactivada.")
    return user


def create_access_token(user: User) -> tuple[str, int]:
    minutes = get_token_expiration()
    now = datetime.now(timezone.utc)
    expiration = now + timedelta(minutes=minutes)
    payload = {
        "sub": str(user.user_id),
        "iss": JWT_ISSUER,
        "iat": now,
        "exp": expiration,
        "type": "access",
    }
    token = jwt.encode(
        payload,
        get_jwt_secret(),
        algorithm=JWT_ALGORITHM,
    )
    return token, minutes * 60


def decode_access_token(token: str) -> int:
    payload = jwt.decode(
        token,
        get_jwt_secret(),
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        options={"require": ["sub", "exp", "iat", "iss", "type"]},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Token no válido.")
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError) as error:
        raise jwt.InvalidTokenError("Usuario no válido.") from error
    if user_id <= 0:
        raise jwt.InvalidTokenError("Usuario no válido.")
    return user_id


def create_guest_token() -> tuple[str, int, UUID]:
    """Genera un token temporal para una sesión de invitado."""
    try:
        minutes = int(os.getenv("GUEST_TOKEN_EXPIRE_MINUTES", "720"))
    except ValueError as error:
        raise AuthServiceError(
            "La expiración de la sesión invitada no es válida."
        ) from error

    if minutes < 15 or minutes > 1440:
        raise AuthServiceError(
            "La sesión invitada debe durar entre 15 y 1440 minutos."
        )

    session_id = uuid4()
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(session_id),
        "iss": JWT_ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        "type": "guest",
    }

    token = jwt.encode(
        payload,
        get_jwt_secret(),
        algorithm=JWT_ALGORITHM,
    )

    return token, minutes * 60, session_id


def decode_guest_token(token: str) -> UUID:
    """Valida un token de invitado y recupera su UUID."""
    payload = jwt.decode(
        token,
        get_jwt_secret(),
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        options={"require": ["sub", "exp", "iat", "iss", "type"]},
    )

    if payload.get("type") != "guest":
        raise jwt.InvalidTokenError("El token no pertenece a un invitado.")

    try:
        return UUID(payload["sub"])
    except (TypeError, ValueError, AttributeError) as error:
        raise jwt.InvalidTokenError(
            "El identificador de la sesión invitada no es válido."
        ) from error
