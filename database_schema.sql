-- ============================================
-- MySQL 数据库表结构设计
-- 用于 RAG 企业文档知识库系统
-- 创建时间: 2026-05-26
-- ============================================

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS rag_knowledge_base 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE rag_knowledge_base;

-- ============================================
-- 部门信息表
-- ============================================
CREATE TABLE IF NOT EXISTS departments (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '部门唯一标识符',
    name VARCHAR(100) NOT NULL COMMENT '部门名称',
    description VARCHAR(255) COMMENT '部门描述',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
  COMMENT='部门信息表';

-- ============================================
-- 文档知识库表
-- ============================================
CREATE TABLE IF NOT EXISTS documents (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '文档唯一标识符',
    file_name VARCHAR(255) NOT NULL COMMENT '文件名',
    file_content LONGTEXT NOT NULL COMMENT '文档文本内容',
    vector_data JSON COMMENT '文档的向量嵌入数据（用于语义搜索）',
    permission_level ENUM('public', 'manager', 'confidential') NOT NULL DEFAULT 'public' 
                      COMMENT '权限等级：public-公开，manager-管理层，confidential-机密',
    department_id INT COMMENT '所属部门ID，关联departments表',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    file_hash VARCHAR(32) COMMENT '文件MD5哈希，用于检测内容变化',
    INDEX idx_permission (permission_level) COMMENT '权限等级索引',
    INDEX idx_department (department_id) COMMENT '部门ID索引',
    INDEX idx_file_hash (file_hash) COMMENT '文件哈希索引，用于增量更新',
    INDEX idx_updated_at (updated_at) COMMENT '更新时间索引',
    FULLTEXT INDEX idx_fulltext_content (file_content) COMMENT '全文索引，用于关键词搜索',
    CONSTRAINT fk_department FOREIGN KEY (department_id) 
        REFERENCES departments(id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
  COMMENT='企业文档知识库表（支持RAG检索）';

-- ============================================
-- 初始化部门数据
-- ============================================
INSERT IGNORE INTO departments (id, name, description) VALUES 
(1, '战略发展部', '负责公司战略规划和业务发展'),
(2, '技术研发部', '负责产品研发和技术创新'),
(3, '人力资源部', '负责人员招聘、培训和员工关系');

-- ============================================
-- 模拟插入文档数据
-- ============================================

-- 文档1：测试.txt（内部公开文档）
INSERT INTO documents (file_name, file_content, permission_level, department_id, file_hash, vector_data) 
VALUES (
    '测试.txt',
    '测试文档内容：《星云科技 2025 年度内部备忘录》
保密级别： 内部公开
发布日期： 2025年3月15日
发布部门： 星云科技战略发展部
一、公司概况与核心产品
星云科技（Nebula Tech）是一家专注于深海探索与能源开发的初创企业。我们的核心产品是"波塞冬三号"（Poseidon-III）深海采矿机器人。该机器人能够在 6000 米深的海底连续作业 30 天，主要任务是采集稀有金属结核。
二、2025 年度关键财务数据
根据第一季度财报显示，星云科技目前的现金流状况良好。
年度研发预算： 5000 万人民币。
单台机器人制造成本： 120 万人民币。
预计单台售价： 450 万人民币。
主要投资方： 蓝鲸资本（Blue Whale Capital）。
三、人事与行政通知
CEO 变更： 原 CEO 张伟因个人原因辞去职务，由原 CTO 李娜接任新任 CEO。
年假政策： 今年起，所有入职满一年的员工，年假天数从 5 天增加至 8 天。
食堂调整： 三楼食堂将于下周一开始装修，期间员工需前往二楼用餐。
四、紧急联系方式
如遇"波塞冬三号"系统故障，请优先联系技术负责人王强，其内部短号为 8899。',
    'public',
    1,
    'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6',
    '{"embedding_model": "text-embedding-ada-002", "dimensions": 1536, "vector": [0.1, 0.2, 0.3]}'
);

-- 文档2：企业内部技术规范文档.docx（管理层文档）
INSERT INTO documents (file_name, file_content, permission_level, department_id, file_hash, vector_data) 
VALUES (
    '企业内部技术规范文档.docx',
    '企业内部技术规范文档
版本：v1.2
部门：技术研发部
一、代码规范
所有代码必须遵循 PEP 8 规范，变量命名采用小写字母加下划线的方式。
二、安全要求
涉及用户数据的接口必须进行权限验证，禁止明文存储密码。
三、文档要求
每个模块必须包含完整的 docstring，说明功能、参数和返回值。
四、测试要求
核心业务逻辑的测试覆盖率必须达到 80% 以上。
五、部署流程
所有代码必须经过 code review 后才能合并到主分支。',
    'manager',
    2,
    'b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7',
    '{"embedding_model": "text-embedding-ada-002", "dimensions": 1536, "vector": [0.2, 0.3, 0.4]}'
);

-- 文档3：员工手册_v2.0.txt.pdf（公开文档）
INSERT INTO documents (file_name, file_content, permission_level, department_id, file_hash, vector_data) 
VALUES (
    '员工手册_v2.0.txt.pdf',
    '星云科技员工手册 v2.0
人力资源部发布
一、入职须知
新员工入职第一天需完成考勤指纹录入、公司门禁卡领取以及工位分配。
二、工作时间
公司实行弹性工作制，核心工作时间为 10:00-16:00。
三、请假制度
事假需提前 3 天申请，病假需提供医院证明。
四、绩效考核
每年 6 月和 12 月进行两次绩效考核。
五、福利政策
五险一金、带薪年假、节日福利、年度体检。',
    'public',
    3,
    'c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8',
    '{"embedding_model": "text-embedding-ada-002", "dimensions": 1536, "vector": [0.3, 0.4, 0.5]}'
);

-- ============================================
-- 常用查询示例
-- ============================================

-- 1. 查询所有公开文档
-- SELECT file_name, file_content, department_id 
-- FROM documents 
-- WHERE permission_level = 'public';

-- 2. 根据用户权限查询可访问文档（假设用户是管理层）
-- SELECT file_name, file_content, permission_level 
-- FROM documents 
-- WHERE permission_level IN ('public', 'manager')
-- ORDER BY permission_level DESC;

-- 3. 查询某个部门的所有文档
-- SELECT d.file_name, d.permission_level, dep.name as department
-- FROM documents d
-- LEFT JOIN departments dep ON d.department_id = dep.id
-- WHERE d.department_id = 1;

-- 4. 检查文档是否更新（通过 file_hash）
-- SELECT file_name, file_hash, updated_at 
-- FROM documents 
-- ORDER BY updated_at DESC;

-- 5. 全文搜索文档内容
-- SELECT file_name, file_content 
-- FROM documents 
-- WHERE MATCH(file_content) AGAINST('深海采矿机器人' IN NATURAL LANGUAGE MODE);
