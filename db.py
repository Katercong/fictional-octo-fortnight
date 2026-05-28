"""
数据库访问层
封装数据库连接与通用查询，统一管理连接生命周期
"""

from config import DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME, DB_TABLE

try:
    import pymysql
except ImportError:
    raise ImportError("请先安装 pymysql: pip install pymysql")


class DatabaseError(Exception):
    """
    数据库操作异常
    """
    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message)
        self.original_error = original_error


def get_connection() -> pymysql.connections.Connection:
    """
    获取数据库连接
    后续可替换为连接池（如 DBUtils.PooledDB）

    Returns:
        pymysql 连接对象

    Raises:
        DatabaseError: 数据库连接失败时抛出
    """
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            charset='utf8mb4'
        )
        return conn
    except Exception as e:
        raise DatabaseError(f"数据库连接失败: {str(e)}", original_error=e)


def execute_query(sql: str, params: tuple = None, fetchone: bool = False, commit: bool = False):
    """
    通用数据库查询函数，统一管理 conn/cursor 的获取与释放

    Args:
        sql: SQL 语句
        params: 参数化查询参数元组
        fetchone: True 返回单行，False 返回多行
        commit: 是否需要提交事务（INSERT/UPDATE/DELETE）

    Returns:
        fetchone=True: 单行元组或 None
        fetchone=False: 多行元组列表
        commit=True: 受影响的行数

    Raises:
        DatabaseError: 查询失败时抛出
    """
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        if commit:
            conn.commit()
            return cursor.rowcount
        elif fetchone:
            return cursor.fetchone()
        else:
            return cursor.fetchall()

    except DatabaseError:
        raise
    except Exception as e:
        raise DatabaseError(f"查询执行失败: {str(e)}", original_error=e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def create_company_files_table():
    """
    创建 company_files 表（如果不存在）

    表结构：
    - id: 自增主键
    - file_name: 文件名
    - file_content: 文件内容（LONGTEXT）
    - permissions: 权限列表，逗号分隔的角色名（如 "admin,employee"）
    - created_at: 创建时间

    Raises:
        DatabaseError: 创建表失败时抛出
    """
    create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {DB_TABLE} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            file_name VARCHAR(255) NOT NULL,
            file_content LONGTEXT NOT NULL,
            permissions VARCHAR(255) NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    execute_query(create_table_sql, commit=True)
    print(f"[数据库] {DB_TABLE} 表已创建或已存在")


def add_test_files():
    """
    插入 3 条测试文件数据（幂等：按 file_name 去重，已存在则跳过）

    1. 仅 admin 可见
    2. 仅 employee 可见
    3. admin 和 employee 都可见

    Raises:
        DatabaseError: 插入失败时抛出
    """
    check_sql = f"SELECT COUNT(*) FROM {DB_TABLE} WHERE file_name = %s"

    test_files = [
        {
            "file_name": "admin_secret.txt",
            "file_content": "【机密文件】仅管理员可见\n\n本文件包含公司核心财务数据：\n- 年度营收：1.2亿\n- 净利润率：18%\n- 研发投入占比：25%",
            "permissions": "admin"
        },
        {
            "file_name": "employee_handbook.txt",
            "file_content": "【员工手册】仅员工可见\n\n新员工入职须知：\n- 工作时间：9:00-18:00\n- 年假：5天起\n- 试用期：3个月",
            "permissions": "employee"
        },
        {
            "file_name": "company_announcement.txt",
            "file_content": "【公司公告】全员可见\n\n关于2026年端午节放假通知：\n- 放假时间：5月31日-6月2日\n- 6月3日正常上班\n- 请大家提前做好工作安排",
            "permissions": "admin,employee"
        }
    ]

    for file_data in test_files:
        existing = execute_query(check_sql, (file_data["file_name"],), fetchone=True)
        if existing and existing[0] > 0:
            print(f"[数据库] 测试文件 {file_data['file_name']} 已存在，跳过")
            continue

        insert_sql = f"""
            INSERT INTO {DB_TABLE} (file_name, file_content, permissions)
            VALUES (%s, %s, %s)
        """
        execute_query(
            insert_sql,
            (file_data["file_name"], file_data["file_content"], file_data["permissions"]),
            commit=True
        )
        print(f"[数据库] 测试文件 {file_data['file_name']} 已插入 (权限: {file_data['permissions']})")
