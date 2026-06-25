from fastapi import Cookie, Depends, HTTPException, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import SECRET_KEY, SESSION_MAX_AGE
from database import PERMISSIONS, get_user_by_id, user_to_dict

serializer = URLSafeTimedSerializer(SECRET_KEY, salt="lotus-session")
COOKIE_NAME = "lotus_session"


def create_session_token(user_id: int) -> str:
    return serializer.dumps({"uid": user_id})


def decode_session_token(token: str) -> int | None:
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE)
        return int(data["uid"])
    except (BadSignature, SignatureExpired, KeyError, ValueError):
        return None


async def get_current_user(lotus_session: str | None = Cookie(default=None)) -> dict:
    if not lotus_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user_id = decode_session_token(lotus_session)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    row = get_user_by_id(user_id)
    if not row or not row["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    return user_to_dict(row)


async def get_optional_user(lotus_session: str | None = Cookie(default=None)) -> dict | None:
    if not lotus_session:
        return None
    user_id = decode_session_token(lotus_session)
    if not user_id:
        return None
    row = get_user_by_id(user_id)
    if not row or not row["is_active"]:
        return None
    return user_to_dict(row)


def require_admin():
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if not user.get("is_admin"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
        return user

    return checker


def require_permission(permission: str):
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if permission not in user.get("permissions", []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {PERMISSIONS.get(permission, permission)}",
            )
        return user

    return checker


def permission_matrix() -> dict:
    return PERMISSIONS.copy()
