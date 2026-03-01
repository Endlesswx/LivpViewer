import sqlite3
import os
import time
import threading
from pathlib import Path


class ThumbnailCache:
    """基于 SQLite 的单文件图片缓存，自动限制最大存储容量 (默认 500MB)。"""

    def __init__(self, db_path: str = "livp_thumbnails.db", max_size_mb: int = 500):
        self.db_path = Path(db_path).absolute()
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self._local = threading.local()
        self._init_db()

    def _init_db(self):
        """初始化数据库表结构。"""
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS thumbnails (
                    file_path TEXT PRIMARY KEY,
                    file_mtime REAL,
                    last_accessed REAL,
                    image_data BLOB
                )
                """
            )
            # 加速主键和访问时间查询
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_last_accessed ON thumbnails(last_accessed)"
            )

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程专属的数据库连接，避免反复开启关闭的昂贵开销。"""
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=10
            )
            # 开启 WAL 模式和内存映射提升读写性能
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return self._local.conn

    def get(self, file_path: str, current_mtime: float) -> bytes:
        """从缓存中获取图片二进制数据。"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT file_mtime, image_data FROM thumbnails WHERE file_path = ?",
            (file_path,)
        )
        row = cursor.fetchone()
        
        if row:
            cached_mtime, image_data = row
            if abs(cached_mtime - current_mtime) < 0.1:  # 容差避免精度问题
                # 更新最后访问时间导致高频写锁阻碍并发读取，取消每次精确更新
                # 依赖于定期或者后台批量更新。此处选择先不更新最后访问时间或仅做极简更新。
                # 由于这是单条获取，保留更新以维持缓存清理逻辑
                try:
                    conn.execute(
                        "UPDATE thumbnails SET last_accessed = ? WHERE file_path = ?",
                        (time.time(), file_path)
                    )
                    conn.commit()
                except sqlite3.OperationalError:
                    pass # 忽略锁超时，不阻塞查询
                return image_data
            else:
                # 文件已修改，被动清理旧的无效记录
                try:
                    conn.execute("DELETE FROM thumbnails WHERE file_path = ?", (file_path,))
                    conn.commit()
                except sqlite3.OperationalError:
                    pass
        
        return None

    def get_many(self, file_paths: list[str], mtimes: dict[str, float]) -> dict[str, bytes]:
        """批量获取缓存中的图片数据。
        
        极大地减少了查询数据库的次数，且查询期间不更新访问时间，避免写锁冲突。
        """
        if not file_paths:
            return {}

        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 构造 IN 查询
        placeholders = ",".join("?" for _ in file_paths)
        query = f"SELECT file_path, file_mtime, image_data FROM thumbnails WHERE file_path IN ({placeholders})"
        
        results = {}
        try:
            cursor.execute(query, tuple(file_paths))
            rows = cursor.fetchall()
            
            for path, cached_mtime, image_data in rows:
                current_mtime = mtimes.get(path, -1)
                # mtime 匹配则认为有效
                if abs(cached_mtime - current_mtime) < 0.1:
                    results[path] = image_data
                else:
                    # mtime不匹配的会被废弃，交由后续的写操作覆盖
                    results[path] = None
        except sqlite3.Error as e:
            print(f"[Cache] 批量查询出错: {e}")
            
        return results

    def put(self, file_path: str, mtime: float, image_data: bytes):
        """将提取出的图片数据写入缓存，如果数据库超过设定上限则触发清理。"""
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO thumbnails (file_path, file_mtime, last_accessed, image_data)
                VALUES (?, ?, ?, ?)
                """,
                (file_path, mtime, time.time(), image_data)
            )
            conn.commit()
        except sqlite3.OperationalError as e:
            print(f"[Cache] 写入锁定: {e}")
        
        self._check_and_cleanup()

    def _check_and_cleanup(self):
        """检查数据库文件大小，若超过 max_size_mb 则清除最旧的 20% 记录并回收空间。"""
        try:
            if not self.db_path.exists():
                return
            
            current_size = self.db_path.stat().st_size
            if current_size <= self.max_size_bytes:
                return

            print(f"[Cache] 触发清理: 当前 {current_size/1024/1024:.2f}MB > 上限 {self.max_size_bytes/1024/1024:.2f}MB")
            
            with sqlite3.connect(
                str(self.db_path),
                timeout=10
            ) as conn:
                # 获取总记录数
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM thumbnails")
                count = cursor.fetchone()[0]
                
                if count > 0:
                    # 删除最旧的 20%
                    delete_count = max(1, int(count * 0.2))
                    conn.execute(
                        """
                        DELETE FROM thumbnails 
                        WHERE file_path IN (
                            SELECT file_path FROM thumbnails 
                            ORDER BY last_accessed ASC 
                            LIMIT ?
                        )
                        """,
                        (delete_count,)
                    )
                    conn.commit()
                
                # 回收释放的物理空间
                conn.execute("VACUUM")
                
            print(f"[Cache] 清理完成: 剩余 {self.db_path.stat().st_size/1024/1024:.2f}MB")
                
        except Exception as e:
            print(f"[Cache] 清理失败: {e}")
