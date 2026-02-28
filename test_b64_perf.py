import sqlite3
import time
import base64
from pathlib import Path

db_path = "livp_thumbnails.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT file_path, file_mtime, image_data FROM thumbnails LIMIT 3000")
rows = c.fetchall()
conn.close()

print("Data loaded, testing base64 encoding...")
t0 = time.time()
b64_list = []
for row in rows:
    img_bytes = row[2]
    if img_bytes:
        b64 = base64.b64encode(img_bytes).decode('utf-8')
        b64_list.append(b64)
t1 = time.time()
print(f"Base64 encoded {len(b64_list)} items in {t1-t0:.4f}s")
