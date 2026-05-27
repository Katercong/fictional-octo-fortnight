"""
请求/响应数据模型
仅存放 API 接口的请求体和响应体模型
认证相关模型（Token, User）保留在 auth.py 中
"""

from pydantic import BaseModel


class LoadDocumentsRequest(BaseModel):
    folder_path: str


class ChatResponse(BaseModel):
    answer: str
    history: list
