"""
向量存储模块
封装 ChromaDB 操作，提供向量检索、添加、清空功能
同时提供向量嵌入计算功能

【隔离改造】
- 全局 chroma_collection 替换为 collection_cache 字典，按 collection_name 缓存
- 所有集合操作函数增加 collection_name 参数，支持按角色动态路由到独立集合
- 命名规则：kb_{role}，不存在时自动创建，存在时直接复用
"""

import chromadb
from config import CHROMA_DB_PATH, CHROMA_COLLECTION_NAME, client, EMBEDDING_MODEL
from exceptions import EmbeddingError

# 全局 ChromaDB 客户端（唯一）
chroma_client = None
# 【隔离改造】按 collection_name 缓存的集合字典，替代原先的单一全局 chroma_collection
collection_cache = {}


def _resolve_collection_name(collection_name: str = None) -> str:
    """
    解析最终使用的 collection 名称
    未指定时回退到 config 中的默认名称

    Args:
        collection_name: 传入的 collection 名称，为 None 时使用默认值

    Returns:
        最终的 collection 名称字符串
    """
    return collection_name if collection_name else CHROMA_COLLECTION_NAME


def get_or_create_collection(collection_name: str = None):
    """
    获取或创建指定名称的 ChromaDB Collection
    命中缓存则直接返回，未命中则创建后缓存

    【隔离改造】核心方法，替代原先的全局 chroma_collection

    Args:
        collection_name: collection 名称，为 None 时使用默认名称

    Returns:
        ChromaDB Collection 对象
    """
    global chroma_client, collection_cache

    name = _resolve_collection_name(collection_name)

    if name not in collection_cache:
        try:
            collection_cache[name] = chroma_client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}
            )
            record_count = collection_cache[name].count()
            print(f"[ChromaDB] 动态获取/创建集合: '{name}'，当前记录数: {record_count}")
        except Exception as e:
            print(f"[ChromaDB] 创建集合 '{name}' 失败: {str(e)}")
            raise

    return collection_cache[name]


def init_chroma():
    """
    初始化 ChromaDB 持久化客户端
    【隔离改造】不再预创建单一集合，集合在首次使用时按需动态创建
    """
    global chroma_client
    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    print(f"[ChromaDB] 向量数据库已连接，路径: {CHROMA_DB_PATH}")
    try:
        init_collection = chroma_client.get_or_create_collection(name="_init_schema_")
        chroma_client.delete_collection(name="_init_schema_")
        print("[ChromaDB] Schema 初始化完成")
    except Exception as e:
        print(f"[ChromaDB] Schema 初始化: {str(e)}")


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


def search_relevant_chunks(query_embedding, top_k=3, collection_name=None):
    """
    根据查询向量检索最相关的文档片段

    【隔离改造】增加 collection_name 参数，检索指定角色的独立集合

    Args:
        query_embedding: 查询文本的向量
        top_k: 返回的最相关片段数量
        collection_name: 目标集合名称，为 None 时使用默认集合

    Returns:
        相关片段列表，每个片段包含 chunk_id、source、content、score
    """
    collection = get_or_create_collection(collection_name)

    if collection.count() == 0:
        return []

    raw_results = collection.query(
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


def add_chunks(embeddings, documents, metadatas, ids, collection_name=None):
    """
    批量添加文档片段到向量数据库

    【隔离改造】增加 collection_name 参数，写入指定角色的独立集合

    Args:
        embeddings: 向量列表
        documents: 文本内容列表
        metadatas: 元数据列表
        ids: ID 列表
        collection_name: 目标集合名称，为 None 时使用默认集合
    """
    collection = get_or_create_collection(collection_name)
    collection.add(
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )


def clear_all(collection_name=None):
    """
    清空集合中的所有数据

    【隔离改造】增加 collection_name 参数，仅清空指定角色的集合

    Args:
        collection_name: 目标集合名称，为 None 时使用默认集合

    Returns:
        被删除的记录数
    """
    collection = get_or_create_collection(collection_name)
    existing_ids = collection.get()['ids']
    if existing_ids:
        collection.delete(ids=existing_ids)
        return len(existing_ids)
    return 0


def get_count(collection_name=None):
    """
    获取集合中的记录数

    【隔离改造】增加 collection_name 参数，查询指定角色的集合记录数

    Args:
        collection_name: 目标集合名称，为 None 时使用默认集合

    Returns:
        记录数
    """
    collection = get_or_create_collection(collection_name)
    return collection.count()
