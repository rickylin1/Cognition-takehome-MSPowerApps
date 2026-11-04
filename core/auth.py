"""Authentication. `get_current_user` is the only place the app decides who the user is."""

import bcrypt
from fastapi import Depends, Request
from sqlalchemy import ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from config import roles as role_config
from core.db import Base, get_db


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def role_names(self) -> list[str]:
        return sorted(r.role for r in self.roles)


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(64), primary_key=True)
    user: Mapped[User] = relationship(back_populates="roles")


class NotAuthenticated(Exception):
    """Raised when a request has no valid session. main.py turns it into a redirect to /login."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_user(db: Session, username: str, password: str, roles: list[str]) -> User:
    unknown = [r for r in roles if r not in role_config.ROLES]
    if unknown:
        raise ValueError(f"Unknown roles: {unknown}")
    user = User(username=username, password_hash=hash_password(password))
    user.roles = [UserRole(role=r) for r in roles]
    db.add(user)
    db.flush()
    return user


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        request.session.clear()
        raise NotAuthenticated()
    request.state.user = user
    return user
