"""User management: Super Administrator only."""
from fastapi import APIRouter, Depends, HTTPException, status
from backend.app.api.deps import require_roles
from backend.app.core.security import hash_password
from backend.app.db.session import get_db
from backend.app.db.store import DuplicateKeyError, Store
from backend.app.models.user import Role, User
from backend.app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_roles(Role.SUPER_ADMIN))])


@router.get("", response_model=list[UserOut])
def list_users(db: Store = Depends(get_db)) -> list[User]:
    return db.find(User, sort=[("id", 1)])


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, db: Store = Depends(get_db)) -> User:
    email = body.email.lower()
    if db.one(User, {"email": email}):
        raise HTTPException(status_code=409, detail="Email already registered")
    if body.role == Role.CENTRE_ADMIN and body.centre_id is None:
        raise HTTPException(status_code=422, detail="centre_id is required for centre_admin")
    user = User(
        email=email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=body.role,
        centre_id=body.centre_id,
    )
    try:
        db.add(user)
    except DuplicateKeyError:  # two requests raced past the check above
        raise HTTPException(status_code=409, detail="Email already registered")
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: Store = Depends(get_db)) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    data = body.model_dump(exclude_unset=True)
    if "password" in data:
        user.hashed_password = hash_password(data.pop("password"))
    for key, value in data.items():
        setattr(user, key, value)
    db.save(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(user_id: int, db: Store = Depends(get_db)) -> None:
    """Soft delete: deactivates the account so audit history stays intact."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    db.update(User, user.id, {"is_active": False})
