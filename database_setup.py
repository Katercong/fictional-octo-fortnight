"""
MySQL 数据库表结构设计和模拟数据插入脚本
用于存储企业文档的 RAG 知识库
"""

import mysql.connector
from datetime import datetime
from dotenv import load_dotenv
import hashlib
import json
import os

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD'),
    'database': os.getenv('MYSQL_DATABASE', 'rag_knowledge_base')
}

DOCUMENTS_TABLE_SQL = """
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
    INDEX idx_permission (permission_level),
    INDEX idx_department (department_id),
    INDEX idx_file_hash (file_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
  COMMENT='企业文档知识库表';
"""

DEPARTMENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS departments (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '部门ID',
    name VARCHAR(100) NOT NULL COMMENT '部门名称',
    description VARCHAR(255) COMMENT '部门描述'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci 
  COMMENT='部门信息表';
"""

SAMPLE_DOCUMENTS = [
    {
        'file_name': '测试.txt',
        'file_content': '''测试文档内容：《星云科技 2025 年度内部备忘录》
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
如遇"波塞冬三号"系统故障，请优先联系技术负责人王强，其内部短号为 8899。''',
        'permission_level': 'public',
        'department_id': 1,
        'vector_data': {
            'embedding_model': 'text-embedding-ada-002',
            'dimensions': 1536,
            'vector': [0.1] * 1536
        }
    },
    {
        'file_name': '企业内部技术规范文档.docx',
        'file_content': '''企业内部技术规范文档
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
所有代码必须经过 code review 后才能合并到主分支。''',
        'permission_level': 'manager',
        'department_id': 2,
        'vector_data': {
            'embedding_model': 'text-embedding-ada-002',
            'dimensions': 1536,
            'vector': [0.2] * 1536
        }
    },
    {
        'file_name': '员工手册_v2.0.txt.pdf',
        'file_content': '''星云科技员工手册 v2.0
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
五险一金、带薪年假、节日福利、年度体检。''',
        'permission_level': 'public',
        'department_id': 3,
        'vector_data': {
            'embedding_model': 'text-embedding-ada-002',
            'dimensions': 1536,
            'vector': [0.3] * 1536
        }
    }
]


def calculate_file_hash(content: str) -> str:
    """计算文件内容的MD5哈希"""
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def init_database():
    """初始化数据库表结构"""
    try:
        db_config_no_db = {
            'host': DB_CONFIG['host'],
            'user': DB_CONFIG['user'],
            'password': DB_CONFIG['password']
        }
        
        conn = mysql.connector.connect(**db_config_no_db)
        cursor = conn.cursor()
        
        cursor.execute("CREATE DATABASE IF NOT EXISTS rag_knowledge_base CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print("✓ 数据库 'rag_knowledge_base' 创建成功")
        
        cursor.close()
        conn.close()
        
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute(DEPARTMENTS_TABLE_SQL)
        print("✓ departments 表创建成功")
        
        cursor.execute(DOCUMENTS_TABLE_SQL)
        print("✓ documents 表创建成功")
        
        cursor.execute("""
            INSERT IGNORE INTO departments (id, name, description) VALUES 
            (1, '战略发展部', '负责公司战略规划和业务发展'),
            (2, '技术研发部', '负责产品研发和技术创新'),
            (3, '人力资源部', '负责人员招聘、培训和员工关系')
        """)
        print("✓ 部门数据初始化成功")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return True
    except mysql.connector.Error as err:
        print(f"数据库初始化失败: {err}")
        return False


def insert_documents():
    """模拟插入文档数据"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        inserted_count = 0
        for doc in SAMPLE_DOCUMENTS:
            file_hash = calculate_file_hash(doc['file_content'])
            
            cursor.execute("""
                SELECT id FROM documents WHERE file_name = %s AND file_hash = %s
            """, (doc['file_name'], file_hash))
            
            existing = cursor.fetchone()
            
            if existing:
                print(f"⏭ 文档 '{doc['file_name']}' 已存在且未更新，跳过")
                continue
            
            vector_json = json.dumps(doc['vector_data'], ensure_ascii=False)
            
            cursor.execute("""
                INSERT INTO documents 
                (file_name, file_content, vector_data, permission_level, department_id, file_hash)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                doc['file_name'],
                doc['file_content'],
                vector_json,
                doc['permission_level'],
                doc['department_id'],
                file_hash
            ))
            
            inserted_count += 1
            print(f"✓ 成功插入文档: '{doc['file_name']}' (权限: {doc['permission_level']})")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"\n✓ 本次共插入 {inserted_count} 个文档")
        return True
        
    except mysql.connector.Error as err:
        print(f"插入文档失败: {err}")
        return False


def query_documents_by_permission(user_level: str = 'public'):
    """根据用户权限查询可访问的文档"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        permission_hierarchy = {'confidential': 0, 'manager': 1, 'public': 2}
        user_level_rank = permission_hierarchy.get(user_level, 2)
        
        accessible_levels = [level for level, rank in permission_hierarchy.items() 
                           if rank <= user_level_rank]
        
        cursor.execute("""
            SELECT d.id, d.file_name, d.permission_level, d.department_id,
                   dep.name as department_name
            FROM documents d
            LEFT JOIN departments dep ON d.department_id = dep.id
            WHERE d.permission_level IN (%s)
            ORDER BY d.permission_level, d.department_id
        """ % ','.join(['%s'] * len(accessible_levels)), accessible_levels)
        
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return results
        
    except mysql.connector.Error as err:
        print(f"查询失败: {err}")
        return []


def main():
    """主函数：执行完整的数据库初始化和文档插入流程"""
    print("=" * 60)
    print("MySQL 数据库初始化和文档插入")
    print("=" * 60)
    
    print("\n[步骤 1] 初始化数据库表结构...")
    if not init_database():
        return
    
    print("\n[步骤 2] 插入文档数据...")
    if not insert_documents():
        return
    
    print("\n[步骤 3] 验证插入结果...")
    print("\n公开文档查询结果（public权限）:")
    public_docs = query_documents_by_permission('public')
    for doc in public_docs:
        print(f"  - {doc['file_name']} ({doc['department_name']})")
    
    print("\n管理层文档查询结果（manager权限）:")
    manager_docs = query_documents_by_permission('manager')
    for doc in manager_docs:
        print(f"  - {doc['file_name']} ({doc['department_name']})")
    
    print("\n" + "=" * 60)
    print("数据库初始化完成！")
    print("=" * 60)


if __name__ == '__main__':
    main()
