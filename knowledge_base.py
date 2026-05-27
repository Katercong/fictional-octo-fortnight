"""
知识库管理模块
负责知识库文件夹同步、文档向量化、定时任务管理
"""

import os
import re
import hashlib
import threading
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from document_parser import extract_text_from_file
from config import KNOWLEDGE_BASE_FOLDER, SYNC_INTERVAL_SECONDS, CHUNK_SIZE, CHUNK_OVERLAP, DB_TABLE
from vector_store import add_chunks, clear_all, get_count, get_embedding
from db import execute_query, DatabaseError
from exceptions import ChunkSplitError

# 知识库文档缓存（内存中）
knowledge_base = {}
# 文件 MD5 记录（用于检测文件变化）
file_md5_records = {}
# 当前知识库文件夹路径
knowledge_base_folder = KNOWLEDGE_BASE_FOLDER
# 后台调度器实例
scheduler = BackgroundScheduler()

def calculate_file_md5(file_path: str) -> str:
    """
    计算文件的 MD5 哈希值，用于检测文件内容是否变化
    
    Args:
        file_path: 文件路径
        
    Returns:
        MD5 哈希字符串，如果失败则返回空字符串
    """
    hash_md5 = hashlib.md5()
    try:
        # 分块读取大文件，避免内存溢出
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"[MD5计算失败] 文件: {file_path}, 错误: {str(e)}")
        return ""


def split_into_chunks(text: str, chunk_size: int = None, overlap: int = None) -> list:
    """
    将长文本切分成适合嵌入模型的片段

    切分策略：
    1. 首先按段落分割
    2. 将段落组合成不超过 chunk_size 的片段
    3. 如果单个段落超过 chunk_size，按句子切分
    4. 最后添加片段间的重叠

    Args:
        text: 输入文本
        chunk_size: 每个片段的最大字符数（默认从 config 读取）
        overlap: 相邻片段的重叠字符数（默认从 config 读取）

    Returns:
        文本片段列表

    Raises:
        ChunkSplitError: 文本分块失败时抛出
    """
    try:
        if chunk_size is None:
            chunk_size = CHUNK_SIZE
        if overlap is None:
            overlap = CHUNK_OVERLAP

        # Step 1: 按空行分割成段落
        paragraphs = re.split(r'\n\s*\n', text)
        # 过滤空段落并去除首尾空白
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        chunks = []
        current_chunk = ""
        for para in paragraphs:
            # 如果当前片段加上新段落不超过大小限制，合并
            if len(current_chunk) + len(para) <= chunk_size:
                current_chunk += para + "\n\n"
            else:
                # 保存当前片段
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                # 如果单个段落就超过大小限制，按句子切分
                if len(para) > chunk_size:
                    # 按句子结束符分割（中文句号、感叹号、问号 + 英文句号、感叹号、问号）
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

        # 添加最后一个片段
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        # Step 2: 添加片段间的重叠
        overlapped_chunks = []
        for i, chunk in enumerate(chunks):
            if i > 0 and overlap > 0:
                # 取前一个片段的最后 overlap 个字符
                prev_tail = chunks[i - 1][-overlap:] if len(chunks[i - 1]) > overlap else chunks[i - 1]
                chunk = prev_tail + "\n" + chunk
            overlapped_chunks.append(chunk)

        return overlapped_chunks

    except Exception as e:
        raise ChunkSplitError(f"文本分块失败: {str(e)}")


def compute_chunk_embeddings():
    """
    启动后台线程计算所有文档片段的向量嵌入并存储到 ChromaDB
    """
    threading.Thread(target=_compute_chunk_embeddings, daemon=True).start()

def _compute_chunk_embeddings():
    """
    实际执行向量计算的函数（在后台线程中运行）
    """
    # 如果知识库为空，清空 ChromaDB 并返回
    if not knowledge_base:
        cleared = clear_all()
        if cleared > 0:
            print(f"[ChromaDB] 已清除 {cleared} 条旧记录（知识库为空）")
        return

    documents = []
    metadatas = []
    ids = []

    # 遍历所有文档，切分成片段
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

    # 如果没有片段，直接返回
    if not ids:
        return

    # Step 1: 清空旧数据
    cleared = clear_all()
    if cleared > 0:
        print(f"[ChromaDB] 已清除 {cleared} 条旧记录")

    total_chunks = len(ids)
    batch_size = 16  # 每批处理 16 个片段
    processed = 0
    failed_count = 0

    # Step 2: 分批计算向量并插入
    while processed < total_chunks:
        batch_end = min(processed + batch_size, total_chunks)
        batch_docs = documents[processed:batch_end]

        embeddings = []
        valid_docs = []
        valid_metas = []
        valid_ids = []

        # 计算当前批次每个片段的向量
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

        # 批量插入到 ChromaDB
        if valid_ids:
            add_chunks(embeddings, valid_docs, valid_metas, valid_ids)

        processed = batch_end
        if processed % batch_size == 0 or processed >= total_chunks:
            print(f"[ChromaDB 索引进度] {processed}/{total_chunks} 个文本片段 (失败: {failed_count})")

    print(f"[ChromaDB 索引完成] 共 {total_chunks - failed_count} 个文本片段已存入向量数据库")

def _scan_folder(folder_path: str, folder_alias: str, current_files: set, supported_extensions: tuple):
    """
    扫描单个文件夹中的文档
    """
    global knowledge_base, file_md5_records
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

                    if relative_path not in file_md5_records or file_md5_records[relative_path] != current_md5:
                        content = extract_text_from_file(file_path)
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

    return new_or_updated_count, skipped_count

def sync_knowledge_base(user_role: str = ""):
    """
    同步知识库文件夹：
    1. 如果 user_role 不为空，从数据库获取该角色有权限的文件到 temp_cache
    2. 扫描 knowledge_base 和 temp_cache 文件夹中的所有支持的文档
    3. 通过 MD5 检测文件变化
    4. 更新内存中的知识库
    5. 如果有变化，触发向量重计算
    
    Args:
        user_role: 用户角色，用于从数据库获取对应权限的文件。为空时跳过数据库拉取。
    """
    global knowledge_base, file_md5_records, knowledge_base_folder

    print(f"\n{'='*50}")
    print(f"[知识库同步] 开始执行")

    # Step 1: 如果 user_role 不为空，从数据库获取该角色有权限的文件
    if user_role:
        print(f"[数据库同步] 开始从数据库获取 {user_role} 角色有权限的文件...")
        try:
            fetch_files_from_db(user_role)
        except Exception as e:
            print(f"[数据库同步] 从数据库获取文件失败（可能数据库未配置）: {str(e)}")
    else:
        print("[数据库同步] user_role 为空，跳过数据库拉取")

    # Step 2: 定义要扫描的文件夹列表
    supported_extensions = ('.txt', '.pdf', '.docx')
    current_files = set()
    total_new_or_updated = 0
    total_skipped = 0

    # 定义需要扫描的文件夹
    scan_folders = [
        (knowledge_base_folder, "knowledge_base")
    ]

    # 添加 temp_cache 文件夹（如果存在）
    temp_cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_cache")
    if os.path.isdir(temp_cache_dir):
        scan_folders.append((temp_cache_dir, "temp_cache"))

    # Step 3: 扫描所有文件夹
    for folder_path, folder_alias in scan_folders:
        if folder_path and os.path.isdir(folder_path):
            new_count, skip_count = _scan_folder(folder_path, folder_alias, current_files, supported_extensions)
            total_new_or_updated += new_count
            total_skipped += skip_count
        elif folder_path:
            print(f"[跳过] 文件夹不存在: {folder_path}")

    # Step 4: 检测已删除的文件
    deleted_files = set(file_md5_records.keys()) - current_files
    if deleted_files:
        print(f"\n[删除检测] 发现已删除的文件:")
        for rel_path in deleted_files:
            print(f"  - {rel_path}")
            del knowledge_base[rel_path]
            del file_md5_records[rel_path]

    print(f"\n[同步完成] 新增/更新: {total_new_or_updated}, 跳过: {total_skipped}, 已删除: {len(deleted_files)}")
    print(f"[知识库状态] 当前文档数量: {len(knowledge_base)}")
    print(f"{'='*50}\n")

    # Step 5: 如果有变化，触发向量重计算
    if total_new_or_updated > 0 or deleted_files:
        compute_chunk_embeddings()

def start_sync_scheduler():
    """
    启动定时同步任务
    """
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
    """
    停止定时同步任务
    """
    scheduler.shutdown()
    print("[关闭] 定时任务已停止")

def set_knowledge_base_folder(folder_path: str):
    """
    设置知识库文件夹路径
    
    Args:
        folder_path: 新的文件夹路径
    """
    global knowledge_base_folder
    knowledge_base_folder = folder_path

def get_knowledge_base_status():
    """
    获取知识库当前状态
    
    Returns:
        包含知识库状态的字典
    """
    return {
        "knowledge_base_folder": knowledge_base_folder,
        "document_count": len(knowledge_base),
        "documents": [
            {"filename": filename, "update_time": doc["update_time"]}
            for filename, doc in knowledge_base.items()
        ],
        "vector_count": get_count()
    }

def fetch_files_from_db(user_role: str) -> list:
    """
    从数据库获取指定角色有权限的文件，并保存到临时缓存目录
    
    Args:
        user_role: 用户角色，用于权限过滤
        
    Returns:
        成功保存的文件路径列表
    """
    temp_cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_cache")
    
    # 确保目录存在
    os.makedirs(temp_cache_dir, exist_ok=True)
    
    # 清空目录下的所有旧文件
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
            print(f"[DB文件缓存] 已保存: {file_name}")
        
        print(f"[DB文件缓存完成] 共保存 {len(saved_files)} 个文件到 {temp_cache_dir}")
        
    except DatabaseError as e:
        print(f"[数据库查询错误] {str(e)}")
    except Exception as e:
        print(f"[文件保存错误] {str(e)}")
    
    return saved_files
