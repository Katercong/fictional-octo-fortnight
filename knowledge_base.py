"""
知识库管理模块
负责知识库文件夹同步、文档向量化、定时任务管理
"""

import os
import hashlib
import threading
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from document_parser import extract_text_from_file
from config import KNOWLEDGE_BASE_FOLDER, SYNC_INTERVAL_SECONDS, SEMANTIC_SEARCH_TOP_K
from vector_store import add_chunks, clear_all, get_count
from embedding import get_embedding, split_into_chunks

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

def sync_knowledge_base():
    """
    同步知识库文件夹：
    1. 扫描文件夹中的所有支持的文档
    2. 通过 MD5 检测文件变化
    3. 更新内存中的知识库
    4. 如果有变化，触发向量重计算
    """
    global knowledge_base, file_md5_records, knowledge_base_folder

    # 检查文件夹是否有效
    if not knowledge_base_folder or not os.path.isdir(knowledge_base_folder):
        print("[知识库同步] 未设置知识库文件夹路径，跳过同步")
        return
    else:
        supported_extensions = ('.txt', '.pdf', '.docx')
        current_files = set()
        new_or_updated_count = 0
        skipped_count = 0

        print(f"\n{'='*50}")
        print(f"[知识库同步] 开始扫描文件夹: {knowledge_base_folder}")

        # 递归遍历文件夹
        for root, _, files in os.walk(knowledge_base_folder):
            for filename in files:
                if filename.lower().endswith(supported_extensions):
                    file_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(file_path, knowledge_base_folder)
                    current_files.add(relative_path)

                    try:
                        # 计算当前文件的 MD5
                        current_md5 = calculate_file_md5(file_path)
                        if not current_md5:
                            print(f"[跳过] 无法计算MD5: {relative_path}")
                            skipped_count += 1
                            continue

                        # 检查文件是新文件还是已更新
                        if relative_path not in file_md5_records or file_md5_records[relative_path] != current_md5:
                            # 提取文件内容
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
                            # 文件未变化，跳过
                            print(f"[无变化] {relative_path} - 跳过")
                            skipped_count += 1

                    except Exception as e:
                        print(f"[错误] 处理文件失败: {relative_path}, 错误: {str(e)}")
                        skipped_count += 1

        # 检测已删除的文件
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

        # 如果有变化，触发向量重计算
        if new_or_updated_count > 0 or deleted_files:
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
