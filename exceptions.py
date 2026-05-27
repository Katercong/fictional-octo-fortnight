"""
异常处理器模块
捕获数据库、JWT、HTTP、请求验证等异常，返回统一 JSON 格式
"""

import traceback
from datetime import datetime

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError


async def global_exception_handler(request: Request, exc: Exception):
    """
    全局异常处理器：捕获所有未处理的异常

    Args:
        request: 请求对象
        exc: 异常对象

    Returns:
        JSON 响应，包含错误信息
    """
    error_message = str(exc)
    status_code = 500

    if "pymysql" in str(type(exc).__module__) or "mysql" in error_message.lower():
        error_message = "数据库连接失败，请稍后重试"
        print(f"[数据库异常] {traceback.format_exc()}")

    elif "jose" in str(type(exc).__module__) or "JWT" in str(type(exc).__name__):
        status_code = 401
        error_message = "令牌无效或已过期"
        print(f"[JWT异常] {traceback.format_exc()}")

    else:
        print(f"[未处理异常] {traceback.format_exc()}")

    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": error_message,
            "timestamp": datetime.now().isoformat()
        }
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """
    HTTP 异常处理器：处理 HTTP 异常

    Args:
        request: 请求对象
        exc: HTTP 异常对象

    Returns:
        JSON 响应，包含错误信息
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
            "timestamp": datetime.now().isoformat()
        }
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    请求验证异常处理器：处理参数验证失败

    Args:
        request: 请求对象
        exc: 验证异常对象

    Returns:
        JSON 响应，包含错误信息
    """
    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "error": "请求参数验证失败",
            "details": exc.errors(),
            "timestamp": datetime.now().isoformat()
        }
    )
