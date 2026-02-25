"""
main.py
职责：Livp Viewer 应用的入口文件。
使用 Flet 框架启动桌面应用并加载 viewer 模块的 UI。
同时实现单实例启动，使得第二次打开文件时“秒开”。
"""

import sys
import socket
import os

PORT = 24567

def try_send_to_running_instance():
    """尝试将命令行参数发送给已运行的实例，成功则说明已有实例在运行"""
    filepath = ""
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        if not os.path.isabs(filepath):
            filepath = os.path.abspath(filepath)
    
    if not filepath:
        # 如果没有传入文件路径，我们仍尝试连接
        # 如果能连上，说明主程序已在运行，可以直接唤醒或忽略
        # 这里发送个特殊标记 "WAKEUP"
        filepath = "WAKEUP"

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.1)  # 快速超时，不阻塞冷启动
            s.connect(("127.0.0.1", PORT))
            s.sendall(filepath.encode("utf-8"))
        return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False

# 在引入重型库(如 flet) 之前，先进行单例检查。
# 这实现了第二次双击文件时真正的“秒打开”。
if try_send_to_running_instance():
    sys.exit(0)

# 如果没有正在运行的实例，继续正常导入和启动
import threading
import flet as ft
from viewer import start_ui

def start_single_instance_server(app_instance):
    """启动本地服务端，监听后续发来的文件路径"""
    def handle_client(conn):
        with conn:
            try:
                data = conn.recv(4096)
                if data:
                    filepath = data.decode("utf-8")
                    if filepath and filepath != "WAKEUP":
                        # 确保UI更新在安全线程中
                        app_instance._open_file_by_path(filepath)
            except Exception as e:
                print(f"处理客户端连接异常: {e}")

    def serve():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", PORT))
            s.listen(5)
            while True:
                try:
                    conn, addr = s.accept()
                    threading.Thread(target=handle_client, args=(conn,), daemon=True).start()
                except Exception:
                    pass

    threading.Thread(target=serve, daemon=True).start()


def main(page: ft.Page):
    """Flet 应用主函数，由 ft.app() 调用，负责初始化页面。"""
    app = start_ui(page)
    start_single_instance_server(app)


if __name__ == "__main__":
    ft.app(target=main)
