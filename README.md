# NebulaRAG 🌌

基于 FastAPI + DeepSeek + ChromaDB 的企业级文档问答 RAG 系统，让 AI 秒懂你的私有文档！

---

## ✨ 特性

- 🧠 **语义检索**：ChromaDB 向量数据库 + `BAAI/bge-m3` 嵌入，毫秒级查询匹配
- 🔄 **自动同步**：每 60 秒自动更新知识库文件变化，实时增量同步
- 📄 **多格式支持**：原生支持 PDF、DOCX、TXT 文档解析
- 💬 **多轮对话**：自带上下文记忆，连贯的对话体验
- 🎨 **简洁前端**：原生 HTML/JS 聊天界面，拖拽上传即用
- 🔐 **安全设计**：JWT 认证、API 密钥、数据库密码通过环境变量管理
- 🛡️ **模块化架构**：单一职责原则，代码高可维护性

---

## 🚀 快速开始

### 1. 环境准备

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填入你的配置：

```env
# SiliconFlow API（必需）
SILICONFLOW_API_KEY=sk-your-key-here
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1

# MySQL 数据库（必需，用于用户认证）
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your-password
MYSQL_DATABASE=rag_knowledge_base
DB_TABLE=company_files

# JWT 认证（必需）
JWT_SECRET_KEY=your-secret-key-here
TOKEN_EXPIRE_MINUTES=30
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
├── main.py                  # 应用入口：创建 app、绑定中间件、注册路由
├── config.py                 # 全局配置：环境变量读取
├── dependencies.py           # 依赖注入：JWT 认证
├── exceptions.py             # 全局异常处理器
├── schemas.py                # 请求/响应数据模型
├── startup.py                # 应用生命周期管理
├── auth.py                   # 用户认证：密码哈希、JWT、频率限制
├── db.py                     # 数据库访问层
├── chat_service.py           # 核心聊天服务：RAG Pipeline
├── knowledge_base.py         # 知识库管理：同步、向量化、定时任务
├── vector_store.py           # ChromaDB 向量数据库操作
├── embedding.py              # 文本向量化
├── document_parser.py        # 文档解析（PDF/DOCX/TXT）
├── routers/                   # API 路由模块
│   ├── __init__.py
│   ├── chat.py               # POST /chat — 聊天问答
│   ├── knowledge.py           # /documents/* /knowledge-base/* — 知识库管理
│   └── users.py               # POST /login GET /users/me — 用户认证
├── index.html                 # 前端聊天界面
├── requirements.txt          # Python 依赖清单
└── .env.example               # 环境变量模板
```

---

## 🧰 模块职责

| 模块 | 职责 |
|------|------|
| `main.py` | 应用组装层，仅绑定中间件和注册路由 |
| `config.py` | 统一读取环境变量，提供配置项 |
| `dependencies.py` | FastAPI 依赖注入：`get_current_user` |
| `exceptions.py` | 全局异常处理：数据库、JWT、HTTP 异常 |
| `schemas.py` | Pydantic 模型：请求/响应数据结构 |
| `startup.py` | 生命周期：`on_startup` / `on_shutdown` |
| `auth.py` | 认证逻辑：密码哈希、JWT 生成、登录频率限制 |
| `db.py` | 数据库访问：统一管理连接、查询、事务 |
| `chat_service.py` | 核心业务：文档检索、上下文组装、AI 生成 |
| `knowledge_base.py` | 知识库：文件夹扫描、文件监控、定时同步 |
| `vector_store.py` | ChromaDB 操作：增删查、相似度匹配 |
| `embedding.py` | 向量化：BAAI/bge-m3 模型调用 |
| `document_parser.py` | 文档解析：PDF/DOCX/TXT 文本提取 |
| `routers/` | API 路由层，按业务域拆分 |

---

## 🔐 API 认证

系统使用 JWT Bearer Token 认证：

```bash
# 1. 登录获取 Token
curl -X POST http://localhost:8000/login \
  -d "username=admin&password=admin123"

# 2. 使用 Token 访问受保护接口
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <your-token>" \
  -F "question=年假政策是什么？"
```

**默认测试账号：**

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin123 | admin |
| employee | emp123 | employee |

---

## 🛡️ 安全特性

- **JWT 认证**：所有敏感接口需携带有效 Token
- **密码哈希**：使用 bcrypt 加密存储
- **参数化查询**：SQL 注入防护
- **频率限制**：登录接口每分钟最多 5 次尝试
- **环境变量**：敏感信息不硬编码

---

## 🧰 技术栈

| 组件 | 选型 |
|------|------|
| Web 框架 | FastAPI |
| LLM API | SiliconFlow / DeepSeek |
| 嵌入模型 | BAAI/bge-m3 |
| 向量库 | ChromaDB |
| 数据库 | MySQL (pymysql) |
| 认证 | JWT (python-jose) + bcrypt |
| 定时任务 | APScheduler |
| 文档解析 | PyPDF2 + python-docx |

---

## 📝 使用说明

1. **知识库自动同步**：修改 `knowledge_base/` 下的文档，系统会在 60 秒内自动检测变更并重新向量化
2. **角色权限**：不同角色从数据库获取不同的文件权限
3. **对话上传**：在聊天界面直接拖拽文件上传，可临时问答该文件内容
4. **API 文档**：启动后访问 `http://127.0.0.1:8000/docs` 查看 OpenAPI 文档

---

## 📄 License

MIT License

---

**Built with ❤️ in 2026**
