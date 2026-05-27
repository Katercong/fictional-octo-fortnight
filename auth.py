"""
用户认证模块
负责用户登录、密码哈希、JWT 令牌生成与验证
"""

from datetime import datetime, timedelta
from typing import Optional, Dict

from jose import JWTError, jwt
from pydantic import BaseModel

from config import JWT_SECRET_KEY, TOKEN_EXPIRE_MINUTES
from db import execute_query, DatabaseError

try:
    import bcrypt
except ImportError:
    raise ImportError("请先安装 bcrypt: pip install bcrypt")

# 登录频率限制 - 内存级存储
login_attempts = {}
MAX_LOGIN_ATTEMPTS = 5
RATE_LIMIT_WINDOW_MINUTES = 1


class User(BaseModel):
    """
    用户模型
    """
    id: int
    username: str
    role: str
    is_active: bool


class Token(BaseModel):
    """
    令牌响应模型
    """
    access_token: str
    token_type: str


class TokenData(BaseModel):
    """
    令牌数据模型
    """
    username: Optional[str] = None


class AuthError(Exception):
    """
    认证相关异常
    """
    pass


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码是否匹配

    Args:
        plain_password: 明文密码
        hashed_password: 哈希密码

    Returns:
        是否匹配
    """
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """
    对密码进行哈希处理

    Args:
        password: 明文密码

    Returns:
        哈希密码
    """
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def check_login_rate_limit(username: str) -> bool:
    """
    检查登录频率限制（每分钟最多5次）

    Args:
        username: 用户名

    Returns:
        是否允许登录（True=允许，False=超过限制）
    """
    now = datetime.now()
    window_start = now - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)

    if username not in login_attempts:
        login_attempts[username] = {"attempts": [], "last_reset": now}

    login_attempts[username]["attempts"] = [
        attempt for attempt in login_attempts[username]["attempts"]
        if attempt > window_start
    ]

    current_attempts = len(login_attempts[username]["attempts"])
    if current_attempts >= MAX_LOGIN_ATTEMPTS:
        return False

    login_attempts[username]["attempts"].append(now)
    return True


def _fetch_user_row(username: str) -> Optional[tuple]:
    """
    从数据库获取用户完整行（内部函数）

    Args:
        username: 用户名

    Returns:
        用户行元组 (id, username, password_hash, role, is_active) 或 None

    Raises:
        DatabaseError: 数据库查询失败时抛出
    """
    query = """
        SELECT id, username, password_hash, role, is_active
        FROM users
        WHERE username = %s
    """
    return execute_query(query, (username,), fetchone=True)


def get_user_by_username(username: str) -> Optional[User]:
    """
    根据用户名从数据库获取用户信息

    Args:
        username: 用户名

    Returns:
        用户对象，不存在返回 None

    Raises:
        DatabaseError: 数据库查询失败时抛出
    """
    row = _fetch_user_row(username)

    if row is None:
        return None

    return User(
        id=row[0],
        username=row[1],
        role=row[3],
        is_active=row[4]
    )


def authenticate_user(username: str, password: str) -> Optional[User]:
    """
    验证用户身份
    复用 _fetch_user_row 结果，仅一次数据库查询完成认证

    Args:
        username: 用户名
        password: 密码

    Returns:
        用户对象（验证成功）或 None（验证失败）

    Raises:
        DatabaseError: 数据库查询失败时抛出
    """
    row = _fetch_user_row(username)

    if row is None:
        return None

    if not row[4]:
        return None

    if not verify_password(password, row[2]):
        print(f"[认证失败] 用户 {username} 密码不匹配")
        return None

    return User(
        id=row[0],
        username=row[1],
        role=row[3],
        is_active=row[4]
    )


def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建 JWT 访问令牌

    Args:
        data: 要编码的数据
        expires_delta: 过期时间

    Returns:
        JWT 令牌字符串
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm="HS256")

    return encoded_jwt


def create_users_table():
    """
    创建 users 表（如果不存在）

    Raises:
        DatabaseError: 创建表失败时抛出
    """
    create_table_sql = """
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL DEFAULT 'employee',
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    execute_query(create_table_sql, commit=True)
    print("[数据库] users 表已创建或已存在")


def add_test_user(username: str, password: str, role: str = "employee"):
    """
    添加测试用户

    Args:
        username: 用户名
        password: 密码
        role: 角色

    Raises:
        DatabaseError: 插入用户失败时抛出
    """
    password_hash = get_password_hash(password)

    insert_sql = """
        INSERT INTO users (username, password_hash, role, is_active)
        VALUES (%s, %s, %s, 1)
        ON DUPLICATE KEY UPDATE
            password_hash = VALUES(password_hash),
            role = VALUES(role),
            is_active = 1;
    """
    execute_query(insert_sql, (username, password_hash, role), commit=True)
    print(f"[数据库] 测试用户 {username} 已添加/更新")
