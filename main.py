"""
main.py
职责：Livp Viewer 应用的入口文件。
使用 Flet 框架启动桌面应用并加载 viewer 模块的 UI。
"""

import flet as ft

from viewer import start_ui


def main(page: ft.Page):
    """Flet 应用主函数，由 ft.app() 调用，负责初始化页面。"""
    start_ui(page)


if __name__ == "__main__":
    ft.run(main)
