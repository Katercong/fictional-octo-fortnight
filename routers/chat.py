"""
聊天路由模块
POST /chat — 用户提问，AI 回答
"""

from fastapi import File, UploadFile, Form, Depends, APIRouter

from schemas import ChatResponse
from dependencies import get_current_user
from auth import User
from knowledge_base import sync_knowledge_base
from chat_service import process_chat
from document_parser import extract_text_from_uploadfile


router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    question: str = Form(None),
    history: str = Form("[]"),
    file: UploadFile = File(None),
    current_user: User = Depends(get_current_user)
):
    print(f"[Chat] 当前用户: {current_user.username}, 角色: {current_user.role}")
    sync_knowledge_base(user_role=current_user.role)

    context_text = ""
    if file:
        context_text = extract_text_from_uploadfile(file)
        file.file.seek(0)

    result = process_chat(question, history, context_text)
    return result
