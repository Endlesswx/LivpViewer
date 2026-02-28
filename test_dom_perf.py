import time
import flet as ft
from base64 import b64encode
import sqlite3

def main(page: ft.Page):
    db_path = "livp_thumbnails.db"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT image_data FROM thumbnails LIMIT 3000")
    rows = c.fetchall()
    conn.close()

    b64_list = [b64encode(r[0]).decode('utf-8') for r in rows if r[0]]
    total = len(b64_list)
    print(f"Loaded {total} b64 strings.")

    grid_view = ft.GridView(
        expand=True,
        max_extent=200,
        child_aspect_ratio=1.0,
        spacing=10,
        run_spacing=10,
    )
    page.add(grid_view)
    
    t0 = time.time()
    
    # Simulate batch creation
    BATCH_SIZE = 30
    for batch_start in range(0, total, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total)
        batch_b64 = b64_list[batch_start:batch_end]
        
        new_cards = []
        for local_i, b64 in enumerate(batch_b64):
            # Create minimal widgets vs actual widgets
            thumbnail = ft.Image(src=f"data:image/jpeg;base64,{b64}", fit="cover")
            card = ft.GestureDetector(content=thumbnail)
            new_cards.append(card)
        
        grid_view.controls.extend(new_cards)
        page.update()
        
    t1 = time.time()
    print(f"Added {total} DOM elements to Flet in {t1-t0:.4f}s")
    page.window.close()

if __name__ == "__main__":
    ft.app(target=main)
