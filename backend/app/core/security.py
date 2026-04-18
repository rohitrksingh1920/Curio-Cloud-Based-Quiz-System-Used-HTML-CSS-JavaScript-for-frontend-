
# from datetime import datetime, timedelta, timezone
# from typing import Optional

# from jose import JWTError, jwt
# from passlib.context import CryptContext
# from fastapi import Depends, HTTPException, status
# from fastapi.security import OAuth2PasswordBearer
# from sqlalchemy.orm import Session

# from backend.app.core.config import settings
# from backend.app.core.database import get_db

# pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# #  Password helpers 

# def hash_password(plain: str) -> str:
#     return pwd_context.hash(plain)


# def verify_password(plain: str, hashed: str) -> bool:
#     return pwd_context.verify(plain, hashed)


# #  JWT helpers 

# def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
#     to_encode = data.copy()
#     expire = datetime.now(timezone.utc) + (
#         expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
#     )
#     to_encode.update({"exp": expire})
#     return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# def decode_token(token: str) -> dict:
#     try:
#         return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
#     except JWTError:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Could not validate credentials",
#             headers={"WWW-Authenticate": "Bearer"},
#         )


# #  Current-user dependency 

# def get_current_user(
#     token: str = Depends(oauth2_scheme),
#     db: Session = Depends(get_db),
# ):
#     # Import here to avoid circular imports at module load time
#     from backend.app.models.user import User

#     payload = decode_token(token)
#     user_id = payload.get("sub")
#     if user_id is None:
#         raise HTTPException(status_code=401, detail="Invalid token payload")

#     user = db.query(User).filter(User.id == int(user_id)).first()
#     if not user:
#         raise HTTPException(status_code=401, detail="User not found")
#     if not user.is_active:
#         raise HTTPException(status_code=403, detail="Inactive account")
#     return user





















"""
backend/app/core/security.py

Provides:
  get_current_user   — any authenticated user
  require_teacher    — admin or teacher only (can create/manage quizzes)
  require_admin      — admin only
  require_student    — student only (rarely needed directly)
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db

pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Current-user dependency ───────────────────────────────────────────────────

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    from backend.app.models.user import User

    payload = decode_token(token)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive account")
    return user


# ── RBAC dependency helpers ───────────────────────────────────────────────────

def require_teacher(current_user=Depends(get_current_user)):
    """
    Allows admin and teacher only.
    Use on: create quiz, edit quiz, delete quiz, enroll students, view full analytics.
    """
    from backend.app.models.user import UserRole
    if current_user.role not in (UserRole.admin, UserRole.teacher):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied — teacher or admin role required",
        )
    return current_user


def require_admin(current_user=Depends(get_current_user)):
    """
    Allows admin only.
    Use on: manage users, change roles, system settings.
    """
    from backend.app.models.user import UserRole
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied — admin role required",
        )
    return current_user
