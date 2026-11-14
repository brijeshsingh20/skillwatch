"""Auth dependencies: current user and role guards."""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from backend.app.core.security import decode_access_token
from backend.app.db.session import get_db
from backend.app.db.store import Store
from backend.app.models.user import Role, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Store = Depends(get_db)) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise unauthorized
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        raise unauthorized
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


def require_roles(*roles: Role):
    """Dependency factory: allow only the listed roles."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return checker


def ensure_centre_access(user: User, centre_id: int) -> None:
    """Centre administrators may only touch their own centre; other roles are not centre-scoped."""
    if user.role == Role.CENTRE_ADMIN and user.centre_id != centre_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your centre")


def get_centre_or_404(db: Store, centre_id: int):
    from backend.app.models import Centre  # local import keeps deps importable without models side effects

    centre = db.get(Centre, centre_id)
    if centre is None:
        raise HTTPException(status_code=404, detail="Centre not found")
    return centre
