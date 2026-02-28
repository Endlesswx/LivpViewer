import flet as ft
import time
import asyncio

async def main(page: ft.Page):
    grid = ft.GridView(expand=True, max_extent=150)
    page.add(grid)
    
    t0 = time.time()
    # Create 3000 minimal placeholders
    placeholders = [ft.Container(bgcolor="grey900", width=150, height=150) for _ in range(3000)]
    grid.controls.extend(placeholders)
    page.update()
    t1 = time.time()
    print(f"Added 3000 placeholders in {t1-t0:.4f}s")
    
    await asyncio.sleep(2)
    page.window.close()   

if __name__ == "__main__":
    ft.app(target=main)
