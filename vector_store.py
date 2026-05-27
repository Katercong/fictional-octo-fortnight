"""
向量存储模块
封装 ChromaDB 操作，提供向量检索、添加、清空功能
同时提供向量嵌入计算功能
"""

import chromadb
from config import CHROMA_DB_PATH, CHROMA_COLLECTION_NAME, client, EMBEDDING_MODEL
from exceptions import EmbeddingError

# 全局 ChromaDB 客户端和集合
chroma_client = None
chroma_collection = None

def init_chroma():
    """
    初始化 ChromaDB：
    1. 创建持久化客户端
    2. 获取或创建集合
    3. 打印初始化信息
    """
    global chroma_client, chroma_collection
    # 创建持久化客户端（数据存储在文件系统中）
    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    # 获取或创建集合，使用余弦相似度
    chroma_collection = chroma_client.get_or_create_collection(
        name=CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    print(f"[ChromaDB] 向量数据库已连接，路径: {CHROMA_DB_PATH}")
    print(f"[ChromaDB] 集合 '{CHROMA_COLLECTION_NAME}' 就绪，当前记录数: {chroma_collection.count()}")


def get_embedding(text: str) -> list:
    """
    调用 API 获取文本的向量嵌入

    Args:
        text: 输入文本

    Returns:
        向量列表

    Raises:
        EmbeddingError: 嵌入计算失败时抛出
    """
    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        raise EmbeddingError(f"向量嵌入计算失败: {str(e)}")


def search_relevant_chunks(query_embedding, top_k=3):
    """
    根据查询向量检索最相关的文档片段
    
    Args:
        query_embedding: 查询文本的向量
        top_k: 返回的最相关片段数量
        
    Returns:
        相关片段列表，每个片段包含 chunk_id、source、content、score
    """
    if chroma_collection is None or chroma_collection.count() == 0:
        return []
    
    # 执行检索
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
            # 将距离转换为相似度分数（0-1 之间，越大越相关）
            # 余弦距离 = 1 - 余弦相似度
            # 这里做一个简单的转换：score = 1 / (1 + distance)
            results.append({
                "chunk_id": chunk_id,
                "source": metadata.get('source', '未知'),
                "content": raw_results['documents'][0][i],
                "score": round(1.0 / (1.0 + distance), 4)
            })
    return results

def add_chunks(embeddings, documents, metadatas, ids):
    """
    批量添加文档片段到向量数据库
    
    Args:
        embeddings: 向量列表
        documents: 文本内容列表
        metadatas: 元数据列表
        ids: ID 列表
    """
    chroma_collection.add(
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )

def clear_all():
    """
    清空集合中的所有数据
    
    Returns:
        被删除的记录数
    """
    existing_ids = chroma_collection.get()['ids']
    if existing_ids:
        chroma_collection.delete(ids=existing_ids)
        return len(existing_ids)
    return 0

def get_count():
    """
    获取集合中的记录数
    
    Returns:
        记录数
    """
    if chroma_collection is None:
        return 0
    return chroma_collection.count()
