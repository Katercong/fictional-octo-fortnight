"""
应用生命周期管理模块
封装 FastAPI 启动和关闭时的初始化与清理逻辑
"""

import os

from config import KNOWLEDGE_BASE_FOLDER
from vector_store import init_chroma
from knowledge_base import sync_knowledge_base, start_sync_scheduler, stop_scheduler
from auth import create_users_table, add_test_user


async def on_startup():
    """
    应用启动时执行：创建数据库表、添加测试用户、初始化向量库、同步知识库
    """
    create_users_table()
    add_test_user("admin", "admin123", "admin")
    add_test_user("employee", "emp123", "employee")

    init_chroma()

    if not os.path.exists(KNOWLEDGE_BASE_FOLDER):
        os.makedirs(KNOWLEDGE_BASE_FOLDER)
        print(f"[初始化] 已创建知识库文件夹: {KNOWLEDGE_BASE_FOLDER}")
    else:
        print(f"[初始化] 知识库文件夹已存在: {KNOWLEDGE_BASE_FOLDER}")

    sync_knowledge_base()
    start_sync_scheduler()


async def on_shutdown():
    """
    应用关闭时执行：停止定时同步任务
    """
    stop_scheduler()
