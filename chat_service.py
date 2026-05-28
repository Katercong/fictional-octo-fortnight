"""
聊天服务模块
负责处理用户请求、检索相关文档、调用 AI 生成回答
"""

import json
from config import client, SYSTEM_PROMPT, MAX_HISTORY_ROUNDS, SEMANTIC_SEARCH_TOP_K
from vector_store import search_relevant_chunks, get_count, get_embedding
from knowledge_base import get_combined_knowledge_base, get_role_collection_name

# 手动加载的文档缓存（临时存储，不持久化）
loaded_documents = []
# 加载的文档文件夹路径
loaded_folder_path = ""

def get_combined_context(query: str = None, user_role: str = "") -> str:
    """
    【合并检索】获取组合上下文：并行检索公共知识库 + 角色专属知识库，合并排序后作为上下文

    Args:
        query: 用户的问题（用于语义检索），如果为空则不做检索
        user_role: 用户角色名，用于路由到对应的 Collection 和知识库缓存

    Returns:
        组合后的上下文文本字符串
    """
    from config import CHROMA_COLLECTION_NAME
    
    context_parts = []

    # Step 1: 如果有查询，执行合并检索
    if query:
        query_embedding = get_embedding(query)
        if query_embedding:
            all_chunks = []
            
            # 1.1 检索公共知识库（始终查询）
            if get_count(CHROMA_COLLECTION_NAME) > 0:
                try:
                    public_chunks = search_relevant_chunks(query_embedding, SEMANTIC_SEARCH_TOP_K, collection_name=CHROMA_COLLECTION_NAME)
                    if public_chunks:
                        all_chunks.extend(public_chunks)
                except Exception as e:
                    print(f"[检索] 公共知识库查询失败: {str(e)}")
            
            # 1.2 检索角色专属知识库（仅当角色有效时查询）
            role_collection_name = get_role_collection_name(user_role)
            if role_collection_name and role_collection_name != CHROMA_COLLECTION_NAME:
                if get_count(role_collection_name) > 0:
                    try:
                        role_chunks = search_relevant_chunks(query_embedding, SEMANTIC_SEARCH_TOP_K, collection_name=role_collection_name)
                        if role_chunks:
                            all_chunks.extend(role_chunks)
                    except Exception as e:
                        print(f"[检索] 角色专属知识库查询失败: {str(e)}")
            
            # 1.3 合并去重、按 score 降序排序、截取前 N 条
            if all_chunks:
                # 去重（基于 chunk_id）
                seen_ids = set()
                unique_chunks = []
                for chunk in all_chunks:
                    if chunk['chunk_id'] not in seen_ids:
                        seen_ids.add(chunk['chunk_id'])
                        unique_chunks.append(chunk)
                
                # 按 score 降序排序
                unique_chunks.sort(key=lambda x: x['score'], reverse=True)
                
                # 截取前 N 条（使用 SEMANTIC_SEARCH_TOP_K 作为合并后的上限）
                top_chunks = unique_chunks[:SEMANTIC_SEARCH_TOP_K]
                
                context_parts.append("【语义检索结果 - 最相关的文档片段】\n")
                for i, chunk in enumerate(top_chunks, 1):
                    context_parts.append(f"--- 相关片段 {i} (来源: {chunk['source']}, 相似度: {chunk['score']}) ---")
                    context_parts.append(chunk['content'])
                    context_parts.append("")

    # Step 2: 如果知识库有文档且没有查询，展示角色合并后的知识库文档
    combined_kb = get_combined_knowledge_base(user_role)
    if combined_kb and not query:
        context_parts.append("【知识库文档】\n")
        for i, (filename, doc) in enumerate(combined_kb.items(), 1):
            context_parts.append(f"--- 文档 {i}: {filename} ---")
            context_parts.append(doc['content'])
            context_parts.append("")

    # Step 3: 添加手动加载的文档
    if loaded_documents:
        context_parts.append("\n【手动加载的文档】\n")
        for i, doc in enumerate(loaded_documents, 1):
            context_parts.append(f"--- 文档 {i}: {doc['filename']} ---")
            context_parts.append(doc['content'])
            context_parts.append("")

    # 将所有部分拼接成一个字符串
    return "\n".join(context_parts).strip()

def parse_documents_in_folder(folder_path: str) -> list:
    """
    解析指定文件夹中的所有支持的文档
    
    Args:
        folder_path: 文件夹路径
        
    Returns:
        文档列表，每个文档包含 filename、file_path、content、modify_time
    """
    global loaded_documents, loaded_folder_path
    from document_parser import extract_text_from_file
    from datetime import datetime
    import os
    
    result = []
    # 支持的文档格式
    supported_extensions = ('.txt', '.pdf', '.docx')

    # 验证路径是否有效
    if not os.path.isdir(folder_path):
        return [{"error": f"路径不是有效的文件夹: {folder_path}"}]

    # 递归遍历文件夹
    for root, _, files in os.walk(folder_path):
        for filename in files:
            if filename.lower().endswith(supported_extensions):
                file_path = os.path.join(root, filename)

                try:
                    # 获取文件修改时间
                    file_stat = os.stat(file_path)
                    modify_time = datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')

                    # 提取文件内容
                    content = extract_text_from_file(file_path)

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

    # 缓存加载的文档
    loaded_documents = result
    loaded_folder_path = folder_path
    return result

def get_documents_status():
    """
    获取当前加载的文档和知识库状态
    
    Returns:
        包含文档状态的字典
    """
    from knowledge_base import get_knowledge_base_status
    
    kb_status = get_knowledge_base_status()
    return {
        "loaded": True if loaded_folder_path else False,
        "loaded_folder_path": loaded_folder_path,
        "loaded_document_count": len(loaded_documents),
        **kb_status
    }

def process_chat(question: str, history: str, context_text: str = "", user_role: str = ""):
    """
    【隔离改造】核心聊天处理函数，增加 user_role 参数实现权限隔离检索

    Args:
        question: 用户的问题
        history: 对话历史 JSON 字符串
        context_text: 额外的上下文文本（如上传的文件内容）
        user_role: 用户角色名，用于路由到角色专属 Collection 和知识库

    Returns:
        包含 answer 和 history 的字典
    """
    try:
        history_list = json.loads(history) if history else []
    except:
        history_list = []

    # 【隔离改造】传递 user_role 到上下文检索
    loaded_context = get_combined_context(question, user_role=user_role)

    # Step 3: 如果没有问题但有文档，默认让 AI 总结文档
    if not question:
        question = "请总结这个文件的内容"

    # Step 4: 整合所有上下文
    all_contexts = []
    if loaded_context:
        all_contexts.append(loaded_context)
    if context_text:
        all_contexts.append(f"【临时文件内容】\n{context_text}")

    current_context = "\n\n".join(all_contexts) if all_contexts else ""

    # Step 5: 构建用户消息（包含上下文和问题）
    user_message = question
    if current_context:
        user_message = f"背景资料:\n{current_context}\n\n问题:\n{question}"

    # Step 6: 构建完整的对话消息列表
    messages = []
    # 添加系统提示词
    messages.append({"role": "system", "content": SYSTEM_PROMPT})

    # 添加历史对话
    for item in history_list:
        if isinstance(item, dict) and "role" in item and "content" in item:
            messages.append({"role": item["role"], "content": item["content"]})

    # 添加当前用户消息
    messages.append({"role": "user", "content": user_message})

    # Step 7: 调用 AI 模型生成回答
    response = client.chat.completions.create(
        model="deepseek-ai/DeepSeek-V4-Flash",  # 使用 DeepSeek V4 Flash 模型
        messages=messages
    )

    # Step 8: 提取 AI 回答
    answer = response.choices[0].message.content

    # Step 9: 更新对话历史
    new_history = history_list.copy()
    # 添加用户消息（保存原始问题，不包含大段上下文）
    history_item = {"role": "user", "content": question}
    if current_context:
        history_item["context"] = current_context
    new_history.append(history_item)
    # 添加 AI 回答
    new_history.append({"role": "assistant", "content": answer})

    # Step 10: 限制历史记录长度，只保留最近的 N 轮
    if len(new_history) > MAX_HISTORY_ROUNDS * 2:
        new_history = new_history[-MAX_HISTORY_ROUNDS * 2:]

    return {"answer": answer, "history": new_history}
