"""
向量嵌入模块
负责将文本转换为向量表示，以及将长文本切分成片段
"""

import re
from config import client, EMBEDDING_MODEL, CHUNK_SIZE, CHUNK_OVERLAP

def get_embedding(text: str) -> list:
    """
    调用 API 获取文本的向量嵌入
    
    Args:
        text: 输入文本
        
    Returns:
        向量列表，如果失败则返回空列表
    """
    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"[嵌入计算失败] {str(e)}")
        return []

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
    """
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
