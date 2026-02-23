"""
test_run.py
职责：带错误捕获的测试启动脚本。
用于调试时捕获并打印完整的异常堆栈信息，便于定位问题。
"""

import traceback

import flet as ft

from main import main

try:
    ft.app(target=main)
except Exception as e:
    print("!!! ERROR START !!!")
    print(traceback.format_exc())
    print("!!! ERROR END !!!")
