"""
依赖注入模块
提供 FastAPI 依赖函数，如 JWT 认证
"""

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from config import JWT_SECRET_KEY
from auth import User, get_user_by_username


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """
    从请求头解析 JWT 令牌并返回当前用户信息

    Args:
        token: JWT 令牌

    Returns:
        当前用户对象

    Raises:
        HTTPException: 令牌无效或用户不存在时抛出 401 错误
    """
    credentials_exception = HTTPException(
        status_code=401,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        username: str = payload.get("sub")

        if username is None:
            raise credentials_exception

        user = get_user_by_username(username)

        if user is None:
            raise credentials_exception

        return user

    except JWTError:
        raise credentials_exception
