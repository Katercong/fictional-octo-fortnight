"""
知识库路由模块
/documents/* — 文档状态与加载
/knowledge-base/* — 知识库文件夹设置与手动同步
"""

import os
from fastapi import HTTPException, APIRouter

from schemas import LoadDocumentsRequest
from config import SYNC_INTERVAL_SECONDS
from chat_service import get_documents_status, parse_documents_in_folder
from knowledge_base import (
    sync_knowledge_base,
    set_knowledge_base_folder,
    get_knowledge_base_status,
    scheduler
)


router = APIRouter(tags=["knowledge"])


@router.get("/documents/status")
async def get_documents_status_endpoint():
    return get_documents_status()


@router.post("/documents/load")
async def load_documents(request: LoadDocumentsRequest):
    documents = parse_documents_in_folder(request.folder_path)

    if documents and "error" in documents[0]:
        raise HTTPException(status_code=400, detail=documents[0]["error"])
    else:
        return {
            "success": True,
            "message": f"成功加载 {len(documents)} 个文档",
            "documents": [{"filename": doc["filename"], "modify_time": doc["modify_time"]} for doc in documents]
        }


@router.post("/knowledge-base/set-folder")
async def set_knowledge_base_folder_endpoint(request: LoadDocumentsRequest):
    if not os.path.isdir(request.folder_path):
        raise HTTPException(status_code=400, detail="无效的文件夹路径")
    else:
        set_knowledge_base_folder(request.folder_path)
        sync_knowledge_base()

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


@router.post("/knowledge-base/sync-now")
async def sync_now():
    sync_knowledge_base()
    status = get_knowledge_base_status()
    return {
        "success": True,
        "message": "手动同步完成",
        "document_count": status["document_count"]
    }
