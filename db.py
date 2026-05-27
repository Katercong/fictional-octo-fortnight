"""
数据库访问层
封装数据库连接与通用查询，统一管理连接生命周期
"""

from config import DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME

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
