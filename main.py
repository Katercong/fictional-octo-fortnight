"""
RAG 系统 FastAPI 主入口文件
提供聊天接口、知识库管理接口和 API 文档
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os

from config import KNOWLEDGE_BASE_FOLDER, SYNC_INTERVAL_SECONDS
from vector_store import init_chroma
from knowledge_base import (
    sync_knowledge_base,
    start_sync_scheduler,
    stop_scheduler,
    set_knowledge_base_folder,
    get_knowledge_base_status,
    scheduler
)
from chat_service import (
    process_chat,
    parse_documents_in_folder,
    get_documents_status
)
from document_parser import extract_text_from_uploadfile

# 初始化 FastAPI 应用
# 自定义 API 文档 URL，将默认的 /docs 和 /redoc 设为 None，后面会自定义
app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json"
)

# 配置 CORS（跨域资源共享）中间件
# 允许前端从不同的域名访问后端接口
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（生产环境建议限制具体域名）
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有请求头
)

# 定义请求体模型：加载文档文件夹的请求
class LoadDocumentsRequest(BaseModel):
    folder_path: str  # 要加载的文档文件夹路径

# 定义响应模型：聊天接口的返回格式
class ChatResponse(BaseModel):
    answer: str  # AI 的回答内容
    history: list  # 更新后的对话历史

# FastAPI 启动事件：应用启动时自动执行
@app.on_event("startup")
async def startup_event():
    # Step 1: 初始化 ChromaDB 向量数据库
    init_chroma()
    
    # Step 2: 检查并创建默认知识库文件夹
    if not os.path.exists(KNOWLEDGE_BASE_FOLDER):
        os.makedirs(KNOWLEDGE_BASE_FOLDER)
        print(f"[初始化] 已创建知识库文件夹: {KNOWLEDGE_BASE_FOLDER}")
    else:
        print(f"[初始化] 知识库文件夹已存在: {KNOWLEDGE_BASE_FOLDER}")
    
    # Step 3: 首次同步知识库
    sync_knowledge_base()
    
    # Step 4: 启动定时同步任务
    start_sync_scheduler()

# FastAPI 关闭事件：应用关闭时自动执行
@app.on_event("shutdown")
async def shutdown_event():
    # 停止定时同步任务
    stop_scheduler()

# 根路径：返回前端聊天界面 HTML
@app.get("/")
async def root():
    return FileResponse("index.html")

# 自定义 Swagger UI 文档页面
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="AI问答API",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )

# 自定义 ReDoc 文档页面
@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url="/openapi.json",
        title="AI问答API",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js",
    )

# 获取文档状态接口
@app.get("/documents/status")
async def get_documents_status_endpoint():
    return get_documents_status()

# 从指定文件夹加载文档接口
@app.post("/documents/load")
async def load_documents(request: LoadDocumentsRequest):
    # 解析文件夹中的所有文档
    documents = parse_documents_in_folder(request.folder_path)

    # 检查是否有错误返回
    if documents and "error" in documents[0]:
        raise HTTPException(status_code=400, detail=documents[0]["error"])
    else:
        # 返回成功响应
        return {
            "success": True,
            "message": f"成功加载 {len(documents)} 个文档",
            "documents": [{"filename": doc["filename"], "modify_time": doc["modify_time"]} for doc in documents]
        }

# 设置知识库文件夹接口
@app.post("/knowledge-base/set-folder")
async def set_knowledge_base_folder_endpoint(request: LoadDocumentsRequest):
    # 验证路径是否有效
    if not os.path.isdir(request.folder_path):
        raise HTTPException(status_code=400, detail="无效的文件夹路径")
    else:
        # 设置新的知识库文件夹路径
        set_knowledge_base_folder(request.folder_path)
        # 立即同步新文件夹
        sync_knowledge_base()

        # 移除旧的定时任务，创建新的定时任务（使用新的路径）
        scheduler.remove_job('knowledge_base_sync')
        scheduler.add_job(
            func=sync_knowledge_base,
            trigger='interval',
            seconds=SYNC_INTERVAL_SECONDS,
            id='knowledge_base_sync',
            name='知识库增量同步',
            replace_existing=True
        )

        return {
            "success": True,
            "message": f"知识库文件夹已设置为: {request.folder_path}",
            "document_count": len(get_knowledge_base_status()["documents"])
        }

# 手动触发知识库同步接口
@app.post("/knowledge-base/sync-now")
async def sync_now():
    sync_knowledge_base()
    status = get_knowledge_base_status()
    return {
        "success": True,
        "message": "手动同步完成",
        "document_count": status["document_count"]
    }

# 核心聊天接口：用户提问，AI 回答
@app.post("/chat", response_model=ChatResponse)
async def chat(
    question: str = Form(None),  # 用户的问题（Form 表单格式）
    history: str = Form("[]"),   # 对话历史（JSON 字符串）
    file: UploadFile = File(None)  # 可选上传的文件
):
    context_text = ""
    # 如果用户上传了文件，提取文件内容作为额外上下文
    if file:
        context_text = extract_text_from_uploadfile(file)
        # 重置文件指针到开头（方便后续可能需要重新读取）
        file.file.seek(0)
    
    # 调用聊天服务处理请求
    result = process_chat(question, history, context_text)
    return result
