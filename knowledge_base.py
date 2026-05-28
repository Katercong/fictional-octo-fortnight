"""
知识库管理模块
负责知识库文件夹同步、文档向量化、定时任务管理

【隔离改造】
- knowledge_base 保留为公共知识库缓存（来自 knowledge_base/ 文件夹）
- 新增 role_kb_cache / role_md5_cache 按角色隔离 DB 文件缓存
- temp_cache 路径按角色隔离：temp_cache/{role}/
- ChromaDB Collection 按角色隔离：kb_{role}
- get_combined_knowledge_base(role) 合并公共 + 角色专属数据
"""

import os
import re
import hashlib
import threading
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from document_parser import extract_text_from_file
from config import KNOWLEDGE_BASE_FOLDER, SYNC_INTERVAL_SECONDS, CHUNK_SIZE, CHUNK_OVERLAP, DB_TABLE, BASE_DIR
from vector_store import add_chunks, clear_all, get_count, get_embedding
from db import execute_query, DatabaseError
from exceptions import ChunkSplitError

# 公共知识库文档缓存（仅 knowledge_base/ 文件夹，所有角色共享）
knowledge_base = {}
# 公共文件 MD5 记录
file_md5_records = {}

# 【隔离改造】按角色隔离的 DB 文件缓存：role -> {relative_path: doc_dict}
role_kb_cache = {}
# 【隔离改造】按角色隔离的 MD5 记录：role -> {relative_path: md5}
role_md5_cache = {}

knowledge_base_folder = KNOWLEDGE_BASE_FOLDER
scheduler = BackgroundScheduler()


def get_role_collection_name(role: str = "") -> str:
    """
    【隔离改造】根据角色名生成对应的 ChromaDB Collection 名称

    Args:
        role: 用户角色名，为空时返回 None（使用默认 Collection）

    Returns:
        Collection 名称字符串，如 "kb_admin"，或 None
    """
    return f"kb_{role}" if role else None


def get_combined_knowledge_base(role: str = "") -> dict:
    """
    【隔离改造】合并公共知识库 + 角色专属 DB 文件

    Args:
        role: 用户角色名，为空时仅返回公共知识库

    Returns:
        合并后的知识库字典
    """
    combined = dict(knowledge_base)
    if role and role in role_kb_cache:
        combined.update(role_kb_cache[role])
    return combined


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
    try:
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

    except Exception as e:
        raise ChunkSplitError(f"文本分块失败: {str(e)}")


def compute_chunk_embeddings(role: str = ""):
    """
    【隔离改造】启动后台线程，将合并后的知识库向量化写入角色专属 Collection

    Args:
        role: 用户角色名，决定目标 Collection
    """
    threading.Thread(target=_compute_chunk_embeddings, args=(role,), daemon=True).start()


def _compute_chunk_embeddings(role: str = ""):
    """
    【隔离改造】实际执行向量计算，写入 kb_{role} Collection

    Args:
        role: 用户角色名
    """
    collection_name = get_role_collection_name(role)
    combined = get_combined_knowledge_base(role)

    if not combined:
        cleared = clear_all(collection_name)
        if cleared > 0:
            print(f"[ChromaDB] 已清除 {cleared} 条旧记录（知识库为空），集合: {collection_name or 'default'}")
        return

    documents = []
    metadatas = []
    ids = []

    for filename, doc in combined.items():
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

    cleared = clear_all(collection_name)
    if cleared > 0:
        print(f"[ChromaDB] 已清除 {cleared} 条旧记录，集合: {collection_name or 'default'}")

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
                print(f"[向量化警告] 文本片段 {ids[processed + j]} 嵌入计算失败")

        if valid_ids:
            add_chunks(embeddings, valid_docs, valid_metas, valid_ids, collection_name=collection_name)

        processed = batch_end
        if processed % batch_size == 0 or processed >= total_chunks:
            print(f"[ChromaDB 索引进度] {processed}/{total_chunks} 个文本片段 (失败: {failed_count}), 集合: {collection_name or 'default'}")

    print(f"[ChromaDB 索引完成] 共 {total_chunks - failed_count} 个文本片段已存入集合: {collection_name or 'default'}")


def _scan_folder(folder_path: str, folder_alias: str, current_files: set,
                 supported_extensions: tuple, target_cache: dict, target_md5: dict):
    """
    【隔离改造】扫描文件夹，结果写入指定的 target_cache / target_md5 字典
    不再直接操作全局 knowledge_base / file_md5_records

    Args:
        folder_path: 要扫描的文件夹路径
        folder_alias: 文件夹别名（用于 relative_path 前缀）
        current_files: 当前扫描到的文件集合（用于删除检测）
        supported_extensions: 支持的文件扩展名元组
        target_cache: 写入目标的文档缓存字典
        target_md5: 写入目标的 MD5 记录字典
    """
    new_or_updated_count = 0
    skipped_count = 0

    if not os.path.isdir(folder_path):
        print(f"[跳过] 文件夹不存在: {folder_path}")
        return new_or_updated_count, skipped_count

    print(f"\n[扫描文件夹] {folder_alias}: {folder_path}")

    for root, _, files in os.walk(folder_path):
        for filename in files:
            if filename.lower().endswith(supported_extensions):
                file_path = os.path.join(root, filename)
                relative_path = f"{folder_alias}/{os.path.relpath(file_path, folder_path)}"
                current_files.add(relative_path)

                try:
                    current_md5 = calculate_file_md5(file_path)
                    if not current_md5:
                        print(f"[跳过] 无法计算MD5: {relative_path}")
                        skipped_count += 1
                        continue

                    if relative_path not in target_md5 or target_md5[relative_path] != current_md5:
                        content = extract_text_from_file(file_path)
                        target_cache[relative_path] = {
                            "content": content,
                            "file_path": file_path,
                            "md5": current_md5,
                            "update_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        target_md5[relative_path] = current_md5

                        print(f"[文件更新] {relative_path} - 内容已更新")
                        new_or_updated_count += 1
                    else:
                        print(f"[无变化] {relative_path} - 跳过")
                        skipped_count += 1

                except Exception as e:
                    print(f"[错误] 处理文件失败: {relative_path}, 错误: {str(e)}")
                    skipped_count += 1

    return new_or_updated_count, skipped_count


def sync_knowledge_base(user_role: str = ""):
    """
    【隔离改造】同步知识库：
    1. 扫描公共 knowledge_base/ 文件夹 -> 更新全局 knowledge_base
    2. 如果 user_role 不为空，从数据库拉取文件到 temp_cache/{role}/
    3. 扫描 temp_cache/{role}/ -> 更新 role_kb_cache[role]
    4. 合并公共 + 角色专属数据，向量化写入 kb_{role} Collection
    5. 如果 user_role 为空（定时任务），仅同步公共知识库到默认 Collection

    Args:
        user_role: 用户角色名，为空时仅同步公共知识库
    """
    print(f"\n{'='*50}")
    print(f"[知识库同步] 开始执行，角色: {user_role or '(公共)'}")

    supported_extensions = ('.txt', '.pdf', '.docx')

    # Step 1: 扫描公共 knowledge_base/ 文件夹
    public_current_files = set()
    public_new, public_skip = _scan_folder(
        knowledge_base_folder, "knowledge_base", public_current_files,
        supported_extensions, knowledge_base, file_md5_records
    )

    # 公共文件删除检测
    deleted_public = set(file_md5_records.keys()) - public_current_files
    for rel_path in deleted_public:
        print(f"[删除检测-公共] {rel_path}")
        del knowledge_base[rel_path]
        del file_md5_records[rel_path]

    total_new = public_new
    total_skip = public_skip
    deleted_count = len(deleted_public)

    # Step 2: 如果有角色，拉取 DB 文件并扫描角色专属目录
    role_current_files = set()
    deleted_role_count = 0

    if user_role:
        # 从数据库拉取文件到 temp_cache/{role}/
        try:
            fetch_files_from_db(user_role)
        except Exception as e:
            print(f"[数据库同步] 获取 {user_role} 角色文件失败: {str(e)}")

        # 【隔离改造】扫描 temp_cache/{role}/ 目录
        role_kb_cache.setdefault(user_role, {})
        role_md5_cache.setdefault(user_role, {})
        role_cache_dir = os.path.join(BASE_DIR, "temp_cache", user_role)

        role_new, role_skip = _scan_folder(
            role_cache_dir, f"temp_cache/{user_role}", role_current_files,
            supported_extensions, role_kb_cache[user_role], role_md5_cache[user_role]
        )

        # 角色文件删除检测
        deleted_role = set(role_md5_cache[user_role].keys()) - role_current_files
        for rel_path in deleted_role:
            print(f"[删除检测-{user_role}] {rel_path}")
            del role_kb_cache[user_role][rel_path]
            del role_md5_cache[user_role][rel_path]
        deleted_role_count = len(deleted_role)

        total_new += role_new
        total_skip += role_skip

    # 汇总
    total_deleted = deleted_count + deleted_role_count
    print(f"\n[同步完成] 新增/更新: {total_new}, 跳过: {total_skip}, 已删除: {total_deleted}")
    combined = get_combined_knowledge_base(user_role)
    print(f"[知识库状态] 公共文档: {len(knowledge_base)}, 角色文档合计: {len(combined)}")
    print(f"{'='*50}\n")

    # Step 3: 如果有变化，触发向量重计算
    if total_new > 0 or total_deleted > 0:
        compute_chunk_embeddings(role=user_role)


def start_sync_scheduler():
    scheduler.add_job(
        func=sync_knowledge_base,
        trigger=IntervalTrigger(seconds=SYNC_INTERVAL_SECONDS),
        id='knowledge_base_sync',
        name='知识库增量同步',
        replace_existing=True
    )
    scheduler.start()
    print(f"[定时任务] 知识库同步任务已启动，每 {SYNC_INTERVAL_SECONDS} 秒执行一次")


def stop_scheduler():
    scheduler.shutdown()
    print("[关闭] 定时任务已停止")


def set_knowledge_base_folder(folder_path: str):
    global knowledge_base_folder
    knowledge_base_folder = folder_path


def get_knowledge_base_status(role: str = ""):
    """
    【隔离改造】获取知识库状态，支持按角色查看

    Args:
        role: 用户角色名，为空时返回公共知识库状态
    """
    combined = get_combined_knowledge_base(role)
    return {
        "knowledge_base_folder": knowledge_base_folder,
        "public_document_count": len(knowledge_base),
        "document_count": len(combined),
        "documents": [
            {"filename": filename, "update_time": doc["update_time"]}
            for filename, doc in combined.items()
        ],
        "vector_count": get_count(get_role_collection_name(role))
    }


def fetch_files_from_db(user_role: str) -> list:
    """
    【隔离改造】从数据库获取指定角色有权限的文件，保存到 temp_cache/{role}/ 目录

    Args:
        user_role: 用户角色，用于权限过滤

    Returns:
        成功保存的文件路径列表
    """
    # 【隔离改造】按角色隔离缓存目录
    temp_cache_dir = os.path.join(BASE_DIR, "temp_cache", user_role)

    os.makedirs(temp_cache_dir, exist_ok=True)

    for filename in os.listdir(temp_cache_dir):
        file_path = os.path.join(temp_cache_dir, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
                print(f"[清理旧文件] 已删除: {filename}")
        except Exception as e:
            print(f"[清理旧文件失败] {filename}: {str(e)}")

    saved_files = []

    try:
        query = f"""
            SELECT file_name, file_content, permissions
            FROM {DB_TABLE}
            WHERE FIND_IN_SET(%s, permissions) > 0
        """

        results = execute_query(query, (user_role,))

        for row in results:
            file_name = row[0]
            file_content = row[1]

            file_path = os.path.join(temp_cache_dir, file_name)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(file_content)

            saved_files.append(file_path)
            print(f"[DB文件缓存-{user_role}] 已保存: {file_name}")

        print(f"[DB文件缓存完成] {user_role} 角色共保存 {len(saved_files)} 个文件到 {temp_cache_dir}")

    except DatabaseError as e:
        print(f"[数据库查询错误] {str(e)}")
    except Exception as e:
        print(f"[文件保存错误] {str(e)}")

    return saved_files
