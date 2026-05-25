from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
from openai import OpenAI
from PyPDF2 import PdfReader
from docx import Document
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
import chromadb
import hashlib
import io
import json
import os
import re
import threading

from document_parser import (
    extract_text_from_file as extract_text_from_file_path
)

load_dotenv()

app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(
    api_key=os.getenv("SILICONFLOW_API_KEY"),
    base_url=os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
)

MAX_HISTORY_ROUNDS = 10
SYSTEM_PROMPT = "你是一个助手，请根据我提供的背景资料回答问题。如果资料里没有答案，请回答不知道。"

loaded_documents = []
loaded_folder_path = ""
file_md5_records = {}
knowledge_base = {}
knowledge_base_folder = ""
scheduler = BackgroundScheduler()

EMBEDDING_MODEL = "BAAI/bge-m3"
SEMANTIC_SEARCH_TOP_K = 3
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
CHROMA_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
CHROMA_COLLECTION_NAME = "rag_knowledge_base"

chroma_client = None
chroma_collection = None

class LoadDocumentsRequest(BaseModel):
    folder_path: str

class ChatResponse(BaseModel):
    answer: str
    history: list

def calculate_file_md5(file_path: str) -> str:
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"[MD5计算失败] 文件: {file_path}, 错误: {str(e)}")
        return ""

def split_into_chunks(text: str, chunk_size: int = None, overlap: int = None) -> list:
    if chunk_size is None:
        chunk_size = CHUNK_SIZE
    if overlap is None:
        overlap = CHUNK_OVERLAP

    paragraphs = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks = []
    current_chunk = ""
    for para in paragraphs:
        if len(current_chunk) + len(para) <= chunk_size:
            current_chunk += para + "\n\n"
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            if len(para) > chunk_size:
                sentences = re.split(r'(?<=[。！？.!?])\s*', para)
                sub_chunk = ""
                for sentence in sentences:
                    if len(sub_chunk) + len(sentence) <= chunk_size:
                        sub_chunk += sentence
                    else:
                        if sub_chunk.strip():
                            chunks.append(sub_chunk.strip())
                        sub_chunk = sentence
                if sub_chunk.strip():
                    chunks.append(sub_chunk.strip())
                current_chunk = ""
            else:
                current_chunk = para + "\n\n"

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    overlapped_chunks = []
    for i, chunk in enumerate(chunks):
        if i > 0 and overlap > 0:
            prev_tail = chunks[i - 1][-overlap:] if len(chunks[i - 1]) > overlap else chunks[i - 1]
            chunk = prev_tail + "\n" + chunk
        overlapped_chunks.append(chunk)

    return overlapped_chunks

def get_embedding(text: str) -> list:
    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"[嵌入计算失败] {str(e)}")
        return []

def compute_chunk_embeddings():
    """启动后台线程执行向量化，避免阻塞主线程/FastAPI 响应"""
    threading.Thread(target=_compute_chunk_embeddings, daemon=True).start()

def _compute_chunk_embeddings():
    global chroma_collection

    if not knowledge_base:
        if chroma_collection:
            existing_ids = chroma_collection.get()['ids']
            if existing_ids:
                chroma_collection.delete(ids=existing_ids)
        return

    documents = []
    metadatas = []
    ids = []

    for filename, doc in knowledge_base.items():
        chunks = split_into_chunks(doc['content'])
        for i, chunk_text in enumerate(chunks):
            chunk_id = f"{filename}__chunk_{i}"
            documents.append(chunk_text)
            metadatas.append({
                "source": filename,
                "chunk_index": i
            })
            ids.append(chunk_id)

    if not ids:
        return

    existing_ids = chroma_collection.get()['ids']
    if existing_ids:
        chroma_collection.delete(ids=existing_ids)
        print(f"[ChromaDB] 已清除 {len(existing_ids)} 条旧记录")

    total_chunks = len(ids)
    batch_size = 16
    processed = 0
    failed_count = 0

    while processed < total_chunks:
        batch_end = min(processed + batch_size, total_chunks)
        batch_docs = documents[processed:batch_end]

        embeddings = []
        valid_docs = []
        valid_metas = []
        valid_ids = []

        for j, doc_text in enumerate(batch_docs):
            emb = get_embedding(doc_text)
            if emb:
                embeddings.append(emb)
                valid_docs.append(doc_text)
                valid_metas.append(metadatas[processed + j])
                valid_ids.append(ids[processed + j])
            else:
                failed_count += 1
                print(f"[向量化警告] 文本块 {ids[processed + j]} 嵌入计算失败")

        if valid_ids:
            chroma_collection.add(
                embeddings=embeddings,
                documents=valid_docs,
                metadatas=valid_metas,
                ids=valid_ids
            )

        processed = batch_end
        if processed % batch_size == 0 or processed >= total_chunks:
            print(f"[ChromaDB 索引进度] {processed}/{total_chunks} 个文本块 (失败: {failed_count})")

    print(f"[ChromaDB 索引完成] 共 {total_chunks - failed_count} 个文本块已存入向量数据库")

def search_relevant_chunks(query: str, top_k: int = None) -> list:
    if top_k is None:
        top_k = SEMANTIC_SEARCH_TOP_K

    if chroma_collection is None or chroma_collection.count() == 0:
        return []

    query_embedding = get_embedding(query)
    if not query_embedding:
        return []

    raw_results = chroma_collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=['documents', 'metadatas', 'distances']
    )

    results = []
    if raw_results and raw_results['ids'] and raw_results['ids'][0]:
        for i, chunk_id in enumerate(raw_results['ids'][0]):
            metadata = raw_results['metadatas'][0][i]
            distance = raw_results['distances'][0][i]
            results.append({
                "chunk_id": chunk_id,
                "source": metadata.get('source', '未知'),
                "content": raw_results['documents'][0][i],
                "score": round(1.0 / (1.0 + distance), 4)
            })

    return results

def extract_text_from_uploadfile(file: UploadFile) -> str:
    filename = file.filename.lower()

    if filename.endswith('.pdf'):
        return extract_text_from_uploadfile_pdf(file)
    elif filename.endswith('.docx'):
        return extract_text_from_uploadfile_docx(file)
    elif filename.endswith('.txt'):
        return extract_text_from_uploadfile_txt(file)
    else:
        return f"不支持的文件格式: {filename}"

def extract_text_from_uploadfile_pdf(file: UploadFile) -> str:
    try:
        reader = PdfReader(file.file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        return f"读取PDF失败: {str(e)}"

def extract_text_from_uploadfile_docx(file: UploadFile) -> str:
    try:
        doc = Document(file.file)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    except Exception as e:
        return f"读取Word失败: {str(e)}"

def extract_text_from_uploadfile_txt(file: UploadFile) -> str:
    try:
        content = file.file.read().decode('utf-8', errors='replace')
        return content.strip()
    except Exception as e:
        return f"读取TXT失败: {str(e)}"


def sync_knowledge_base():
    global knowledge_base, file_md5_records, knowledge_base_folder

    if not knowledge_base_folder or not os.path.isdir(knowledge_base_folder):
        print("[知识库同步] 未设置知识库文件夹路径，跳过同步")
        return

    supported_extensions = ('.txt', '.pdf', '.docx')
    current_files = set()
    new_or_updated_count = 0
    skipped_count = 0

    print(f"\n{'='*50}")
    print(f"[知识库同步] 开始扫描文件夹: {knowledge_base_folder}")

    for root, _, files in os.walk(knowledge_base_folder):
        for filename in files:
            if filename.lower().endswith(supported_extensions):
                file_path = os.path.join(root, filename)
                relative_path = os.path.relpath(file_path, knowledge_base_folder)
                current_files.add(relative_path)

                try:
                    current_md5 = calculate_file_md5(file_path)
                    if not current_md5:
                        print(f"[跳过] 无法计算MD5: {relative_path}")
                        skipped_count += 1
                        continue

                    if relative_path not in file_md5_records or file_md5_records[relative_path] != current_md5:
                        content = extract_text_from_file_path(file_path)
                        knowledge_base[relative_path] = {
                            "content": content,
                            "file_path": file_path,
                            "md5": current_md5,
                            "update_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        file_md5_records[relative_path] = current_md5

                        print(f"[文件更新] {relative_path} - 内容已更新")
                        new_or_updated_count += 1
                    else:
                        print(f"[无变化] {relative_path} - 跳过")
                        skipped_count += 1

                except Exception as e:
                    print(f"[错误] 处理文件失败: {relative_path}, 错误: {str(e)}")
                    skipped_count += 1

    deleted_files = set(file_md5_records.keys()) - current_files
    if deleted_files:
        print(f"\n[删除检测] 发现已删除的文件:")
        for rel_path in deleted_files:
            print(f"  - {rel_path}")
            del knowledge_base[rel_path]
            del file_md5_records[rel_path]

    print(f"\n[同步完成] 新增/更新: {new_or_updated_count}, 跳过: {skipped_count}, 已删除: {len(deleted_files)}")
    print(f"[知识库状态] 当前文档数量: {len(knowledge_base)}")
    print(f"{'='*50}\n")

    if new_or_updated_count > 0 or deleted_files:
        compute_chunk_embeddings()

def start_knowledge_base_sync():
    global knowledge_base_folder

    sync_knowledge_base()

    scheduler.add_job(
        func=sync_knowledge_base,
        trigger=IntervalTrigger(seconds=60),
        id='knowledge_base_sync',
        name='知识库增量同步',
        replace_existing=True
    )
    scheduler.start()
    print(f"[定时任务] 知识库同步任务已启动，每 60 秒执行一次")

def parse_documents_in_folder(folder_path: str) -> list:
    global loaded_documents, loaded_folder_path
    result = []
    supported_extensions = ('.txt', '.pdf', '.docx')

    if not os.path.isdir(folder_path):
        return [{"error": f"路径不是有效的文件夹: {folder_path}"}]

    for root, _, files in os.walk(folder_path):
        for filename in files:
            if filename.lower().endswith(supported_extensions):
                file_path = os.path.join(root, filename)

                try:
                    file_stat = os.stat(file_path)
                    modify_time = datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')

                    content = extract_text_from_file_path(file_path)

                    result.append({
                        "filename": filename,
                        "file_path": file_path,
                        "content": content,
                        "modify_time": modify_time
                    })
                except Exception as e:
                    result.append({
                        "filename": filename,
                        "file_path": file_path,
                        "content": f"处理文件时发生错误: {str(e)}",
                        "modify_time": "未知"
                    })

    loaded_documents = result
    loaded_folder_path = folder_path
    return result

def get_combined_context(query: str = None) -> str:
    context_parts = []

    if query and chroma_collection is not None and chroma_collection.count() > 0:
        relevant_chunks = search_relevant_chunks(query, SEMANTIC_SEARCH_TOP_K)
        if relevant_chunks:
            context_parts.append("【语义检索结果 - 最相关的文档片段】\n")
            for i, chunk in enumerate(relevant_chunks, 1):
                context_parts.append(f"--- 相关片段 {i} (来源: {chunk['source']}, 相似度: {chunk['score']}) ---")
                context_parts.append(chunk['content'])
                context_parts.append("")

    if knowledge_base and not query:
        context_parts.append("【知识库文档】\n")
        for i, (filename, doc) in enumerate(knowledge_base.items(), 1):
            context_parts.append(f"--- 文档 {i}: {filename} ---")
            context_parts.append(doc['content'])
            context_parts.append("")

    if loaded_documents:
        context_parts.append("\n【手动加载的文档】\n")
        for i, doc in enumerate(loaded_documents, 1):
            context_parts.append(f"--- 文档 {i}: {doc['filename']} ---")
            context_parts.append(doc['content'])
            context_parts.append("")

    return "\n".join(context_parts).strip()

@app.on_event("startup")
async def startup_event():
    global knowledge_base_folder, chroma_client, chroma_collection

    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    chroma_collection = chroma_client.get_or_create_collection(
        name=CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    print(f"[ChromaDB] 向量数据库已连接，路径: {CHROMA_DB_PATH}")
    print(f"[ChromaDB] 集合 '{CHROMA_COLLECTION_NAME}' 就绪，当前记录数: {chroma_collection.count()}")

    knowledge_base_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge_base")

    if not os.path.exists(knowledge_base_folder):
        os.makedirs(knowledge_base_folder)
        print(f"[初始化] 已创建知识库文件夹: {knowledge_base_folder}")
    else:
        print(f"[初始化] 知识库文件夹已存在: {knowledge_base_folder}")

    start_knowledge_base_sync()

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    print("[关闭] 定时任务已停止")

@app.get("/")
async def root():
    return {"message": "AI项目启动成功"}

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="AI问答API",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )

@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url="/openapi.json",
        title="AI问答API",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js",
    )

@app.get("/documents/status")
async def get_documents_status():
    return {
        "loaded": True if loaded_folder_path else False,
        "loaded_folder_path": loaded_folder_path,
        "loaded_document_count": len(loaded_documents),
        "knowledge_base_folder": knowledge_base_folder,
        "knowledge_base_count": len(knowledge_base),
        "knowledge_base_documents": [
            {"filename": filename, "update_time": doc["update_time"]}
            for filename, doc in knowledge_base.items()
        ]
    }

@app.post("/documents/load")
async def load_documents(request: LoadDocumentsRequest):
    documents = parse_documents_in_folder(request.folder_path)

    if "error" in documents[0] if documents else False:
        raise HTTPException(status_code=400, detail=documents[0]["error"])

    return {
        "success": True,
        "message": f"成功加载 {len(documents)} 个文档",
        "documents": [{"filename": doc["filename"], "modify_time": doc["modify_time"]} for doc in documents]
    }

@app.post("/knowledge-base/set-folder")
async def set_knowledge_base_folder(request: LoadDocumentsRequest):
    global knowledge_base_folder

    if not os.path.isdir(request.folder_path):
        raise HTTPException(status_code=400, detail="无效的文件夹路径")

    knowledge_base_folder = request.folder_path
    sync_knowledge_base()

    scheduler.remove_job('knowledge_base_sync')
    scheduler.add_job(
        func=sync_knowledge_base,
        trigger=IntervalTrigger(seconds=60),
        id='knowledge_base_sync',
        name='知识库增量同步',
        replace_existing=True
    )

    return {
        "success": True,
        "message": f"知识库文件夹已设置为: {knowledge_base_folder}",
        "document_count": len(knowledge_base)
    }

@app.post("/knowledge-base/sync-now")
async def sync_now():
    sync_knowledge_base()
    return {
        "success": True,
        "message": "手动同步完成",
        "document_count": len(knowledge_base)
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(
    question: str = Form(None),
    history: str = Form("[]"),
    file: UploadFile = File(None)
):
    try:
        history_list = json.loads(history) if history else []
    except:
        history_list = []

    context_text = ""
    if file:
        context_text = extract_text_from_uploadfile(file)
        file.file.seek(0)

    loaded_context = get_combined_context(question)

    if not question:
        question = "请总结这个文件的内容"

    all_contexts = []
    if loaded_context:
        all_contexts.append(loaded_context)
    if context_text:
        all_contexts.append(f"【临时文件内容】\n{context_text}")

    current_context = "\n\n".join(all_contexts) if all_contexts else ""

    user_message = question
    if current_context:
        user_message = f"背景资料:\n{current_context}\n\n问题:\n{question}"

    messages = []
    messages.append({"role": "system", "content": SYSTEM_PROMPT})

    for item in history_list:
        if isinstance(item, dict) and "role" in item and "content" in item:
            messages.append({"role": item["role"], "content": item["content"]})

    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="deepseek-ai/DeepSeek-V4-Flash",
        messages=messages
    )

    answer = response.choices[0].message.content

    new_history = history_list.copy()
    history_item = {"role": "user", "content": question}
    if current_context:
        history_item["context"] = current_context
    new_history.append(history_item)
    new_history.append({"role": "assistant", "content": answer})

    if len(new_history) > MAX_HISTORY_ROUNDS * 2:
        new_history = new_history[-MAX_HISTORY_ROUNDS * 2:]

    return {"answer": answer, "history": new_history}