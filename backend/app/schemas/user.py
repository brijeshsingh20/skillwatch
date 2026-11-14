from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.app.models.user import Role

# Plain format check instead of EmailStr: the email-validator library rejects reserved domains such as
# ".local", which the demo accounts use. Real deliverability is not needed (the app never sends email).
Email = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=255,
                                         pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]


class UserCreate(BaseModel):
    email: Email
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: Role
    centre_id: int | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: Role | None = None
    centre_id: int | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: Role
    centre_id: int | None
    is_active: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
