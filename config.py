"""
RAG 系统配置文件
包含所有全局配置参数和 API 客户端初始化
"""

from dotenv import load_dotenv
from openai import OpenAI
import os

# 加载 .env 文件中的环境变量（如 API 密钥、数据库配置等）
load_dotenv()

# 对话历史保留的最大轮数（每轮包含一条用户消息和一条助手回复）
MAX_HISTORY_ROUNDS = 10

# 系统提示词：定义 AI 助手的行为准则和回答风格
SYSTEM_PROMPT = """
你是 NebulaRAG 的 AI 文档问答助手。

你的任务是：
基于检索到的知识库内容，准确回答用户问题。

【严格规则】

- 只能使用提供的上下文信息回答
- 禁止使用训练数据中的外部知识
- 禁止编造不存在的信息
- 如果上下文无法回答问题，必须明确说明：
  “知识库中没有相关信息”
- 优先引用上下文中的原始术语与表达
- 回答应保持技术准确性
- 不要输出无关内容

【回答风格】

- 简洁清晰
- 技术问题优先使用分点
- 避免重复
- 保持专业语气

【输出格式】

如果能回答：

回答：
<answer>

如果不能回答：

回答：
知识库中没有相关信息。

【上下文】
{context}

【用户问题】
{question}

请开始回答：
"""

# 嵌入模型：用于将文本转换为向量的模型
EMBEDDING_MODEL = "BAAI/bge-m3"

# 语义搜索返回的最相关文档片段数量（Top-K 检索）
SEMANTIC_SEARCH_TOP_K = 3

# 文本分块大小：将文档切分为多少字符的片段
CHUNK_SIZE = 500

# 分块重叠大小：相邻块之间重叠的字符数，避免语义割裂
CHUNK_OVERLAP = 100

# 知识库自动同步间隔（单位：秒）
SYNC_INTERVAL_SECONDS = 60

# 项目根目录路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ChromaDB 向量数据库存储路径
CHROMA_DB_PATH = os.path.join(BASE_DIR, "chroma_db")

# ChromaDB 集合名称（相当于数据库表）
CHROMA_COLLECTION_NAME = "rag_knowledge_base"

# 知识库默认文件夹路径
KNOWLEDGE_BASE_FOLDER = os.path.join(BASE_DIR, "knowledge_base")

# 数据库配置 (Database Config)
DB_HOST = os.getenv("MYSQL_HOST", "localhost")   # 数据库地址，对应 .env 中的 MYSQL_HOST
DB_PORT = int(os.getenv("MYSQL_PORT", 3306))    # 端口，默认 3306
DB_USER = os.getenv("MYSQL_USER", "root")       # 用户名，对应 .env 中的 MYSQL_USER
DB_PASS = os.getenv("MYSQL_PASSWORD", "")       # 密码，对应 .env 中的 MYSQL_PASSWORD
DB_NAME = os.getenv("MYSQL_DATABASE", "")       # 数据库名，对应 .env 中的 MYSQL_DATABASE
DB_TABLE = os.getenv("DB_TABLE", "company_files") # 存放文件的表名

# 初始化 OpenAI 兼容的 API 客户端（连接到 SiliconFlow）
client = OpenAI(
    # 从环境变量读取 API 密钥
    api_key=os.getenv("SILICONFLOW_API_KEY"),
    # 从环境变量读取 API 基础 URL，默认是 SiliconFlow 的地址
    base_url=os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
)