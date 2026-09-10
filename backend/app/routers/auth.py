from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, security

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """§8 JWT 登录。Swagger 页面可直接用 Authorize 调用。"""
    user = db.query(models.User).filter(models.User.username == form.username).first()
    if not user or not security.verify_password(form.password, user.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if user.status != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")
    token = security.create_token(user.username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user.username,
        "role": user.role,
    }


@router.get("/me")
def me(user: models.User = Depends(security.get_current_user_obj)):
    """当前登录用户信息（前端刷新页面时用于恢复角色）。"""
    return {"username": user.username, "role": user.role}
