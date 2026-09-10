from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_MINUTES
from .database import get_db
from . import models

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_token(username: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": username, "exp": exp}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str):
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def get_current_user(token: str = Depends(oauth2)) -> str:
    """§8 用户认证：校验 JWT Bearer，返回 username。"""
    try:
        payload = decode_token(token)
        username = payload.get("sub")
        if not username:
            raise JWTError("missing sub")
        return username
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_obj(
    db: Session = Depends(get_db),
    username: str = Depends(get_current_user),
) -> models.User:
    """返回当前登录用户对象（含 role / status）。"""
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or user.status != 1:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不存在或已禁用")
    return user


def require_admin(
    db: Session = Depends(get_db),
    username: str = Depends(get_current_user),
) -> str:
    """管理员专属接口依赖：非 admin 一律 403。"""
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return username
