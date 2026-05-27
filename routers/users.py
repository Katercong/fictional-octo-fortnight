"""
用户路由模块
POST /login — 用户登录
GET /users/me — 获取当前用户信息
"""

from fastapi import Depends, HTTPException, APIRouter
from fastapi.security import OAuth2PasswordRequestForm

from auth import (
    authenticate_user,
    create_access_token,
    check_login_rate_limit,
    RATE_LIMIT_WINDOW_MINUTES,
    Token,
    User
)
from dependencies import get_current_user


router = APIRouter(tags=["users"])


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    用户登录接口

    Args:
        form_data: 包含 username 和 password 的表单数据

    Returns:
        包含 access_token 和 token_type 的响应

    Raises:
        HTTPException: 用户名或密码错误时抛出 401 错误
        HTTPException: 登录频率超过限制时抛出 429 错误
    """
    if not check_login_rate_limit(form_data.username):
        raise HTTPException(
            status_code=429,
            detail=f"登录过于频繁，请等待 {RATE_LIMIT_WINDOW_MINUTES} 分钟后再试",
            headers={"Retry-After": str(RATE_LIMIT_WINDOW_MINUTES * 60)},
        )

    user = authenticate_user(form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.username})

    print(f"[登录成功] 用户: {user.username}, 角色: {user.role}")

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    """
    获取当前登录用户信息

    Args:
        current_user: 当前用户对象（通过 JWT 令牌解析获得）

    Returns:
        用户信息（不包含密码哈希）
    """
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "is_active": current_user.is_active
    }
