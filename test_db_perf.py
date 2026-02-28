import sqlite3
import time
from pathlib import Path

db_path = "livp_thumbnails.db"
if not Path(db_path).exists():
    print(f"{db_path} does not exist")
else:
    t0 = time.time()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM thumbnails")
    count = c.fetchone()[0]
    t1 = time.time()
    print(f"Count: {count}, Time to count: {t1-t0:.4f}s")
    
    t0 = time.time()
    c.execute("SELECT file_path, file_mtime FROM thumbnails")
    rows = c.fetchall()
    t1 = time.time()
    print(f"Fetched {len(rows)} metadata rows in {t1-t0:.4f}s")

    # simulate fetching 3000 rows
    limit = min(3000, count)
    if limit > 0:
        t0 = time.time()
        c.execute(f"SELECT file_path, file_mtime, image_data FROM thumbnails LIMIT {limit}")
        rows = c.fetchall()
        t1 = time.time()
        total_size = sum(len(r[2]) for r in rows if r[2])
        print(f"Fetched {len(rows)} data rows ({total_size/1024/1024:.2f} MB) in {t1-t0:.4f}s")
    
    conn.close()
