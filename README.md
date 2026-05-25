# NebulaRAG 🌌

基于 FastAPI + DeepSeek + ChromaDB 的企业级文档问答 RAG 系统，让 AI 秒懂你的私有文档！

---

## ✨ 特性

- 🧠 **语义检索**：ChromaDB 向量数据库 + `BAAI/bge-m3` 嵌入，毫秒级查询匹配
- 🔄 **自动同步**：每 60 秒自动更新知识库文件变化，实时增量同步
- 📄 **多格式支持**：原生支持 PDF、DOCX、TXT 文档解析
- 💬 **多轮对话**：自带上下文记忆，连贯的对话体验
- 🎨 **简洁前端**：原生 HTML/JS 聊天界面，拖拽上传即用
- 🔐 **安全设计**：API 密钥、数据库密码通过环境变量管理，代码中无硬编码

---

## 🚀 快速开始

### 1. 环境准备

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填入你的配置：

```env
SILICONFLOW_API_KEY=sk-your-key-here
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1

# MySQL（可选，用于数据库示例，RAG 主流程用 ChromaDB）
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your-password
MYSQL_DATABASE=rag_knowledge_base
```

### 3. 准备知识库

在项目根目录下创建 `knowledge_base/` 文件夹，放入你的文档即可。支持 `.pdf`/`.docx`/`.txt`。

### 4. 启动服务

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

打开浏览器访问：`http://127.0.0.1:8000` 即可开始使用！

---

## 📁 项目结构

```
NebulaRAG/
├── main.py                # FastAPI 后端核心逻辑
├── document_parser.py     # 文档解析模块（与 main.py 共享）
├── database_setup.py      # MySQL 示例数据库初始化脚本
├── database_schema.sql    # MySQL 表结构定义
├── index.html             # 前端聊天界面
├── requirements.txt       # Python 依赖清单
└── .env.example           # 环境变量模板
```

---

## 🧰 技术栈

| 组件 | 选型 |
|-----|------|
| Web 框架 | FastAPI 0.109.0 |
| LLM API | SiliconFlow / DeepSeek |
| 嵌入模型 | BAAI/bge-m3 |
| 向量库 | ChromaDB 0.4.24 |
| 定时任务 | APScheduler 3.10.4 |
| 文档解析 | PyPDF2 + python-docx |

---

## 📝 使用说明

1. **知识库自动同步**：修改 `knowledge_base/` 下的文档，系统会在 60 秒内自动检测变更并重新向量化
2. **对话上传**：在聊天界面直接拖拽文件上传，可临时问答该文件内容
3. **API 文档**：启动后访问 `http://127.0.0.1:8000/docs` 查看 OpenAPI 文档

---

## 📄 License

MIT License

---

**Built with ❤️ in 2026**
