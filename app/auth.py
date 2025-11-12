from typing import Optional
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from db import User
import uuid

# Use PBKDF2 to avoid bcrypt's 72-byte password limit and backend issues
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_user(db: Session, email: str, password: str) -> User:
    email = (email or "").strip().lower()
    if not email or not password:
        raise ValueError("Email and password are required")
    # Enforce unique email
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise ValueError("An account with this email already exists")
    # Derive a username for internal use (local-part)
    username = email.split("@")[0] if "@" in email else email
    user = User(username=username, email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.email == (email or "").strip().lower()).first()
    if not user:
        return None
    if not verify_password(password or "", user.password_hash):
        return None
    return user


def upsert_user_oauth(
    db: Session,
    *,
    provider: str,
    provider_id: str,
    email: Optional[str],
    name: Optional[str] = None,
) -> User:
    """Find or create a user based on OAuth identity.

    - If a user exists with provider+provider_id, return it.
    - Else if a user exists with the same email, attach provider info to that user.
    - Else create a new user with derived username and a random password hash.
    """
    # 1) Match by provider id
    u = db.query(User).filter(User.provider == provider, User.provider_id == provider_id).first()
    if u:
        return u

    # 2) Match by email if provided
    if email:
        u = db.query(User).filter(User.email == email.lower()).first()
        if u:
            u.provider = provider
            u.provider_id = provider_id
            db.add(u)
            db.commit()
            db.refresh(u)
            return u

    # 3) Create new user
    email_norm = (email or "").strip().lower() or None
    username_base = (email_norm.split("@")[0] if email_norm and "@" in email_norm else (name or "user")).strip()
    # Ensure unique username by appending suffix if needed
    candidate = username_base or "user"
    i = 1
    while db.query(User).filter(User.username == candidate).first() is not None:
        i += 1
        candidate = f"{username_base}{i}"

    user = User(
        username=candidate,
        email=email_norm,
        password_hash=hash_password(uuid.uuid4().hex),
        provider=provider,
        provider_id=provider_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
