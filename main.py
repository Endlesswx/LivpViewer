"""
main.py
职责：Livp Viewer 应用的入口文件。
使用 Flet 框架启动桌面应用并加载 viewer 模块的 UI。

启动策略：
  - 单例模式：若已有实例正在运行，发送 WAKEUP 信号唤醒其窗口后直接退出，
    实现"第二次打开秒弹窗"。
  - 窗口延迟展示：启动时先隐藏窗口（避免白屏闪烁），Flet 初始化完成后
    再淡入显示，提升视觉体验。
  - 后台驻留：关闭窗口时不退出进程，而是隐藏到后台；再次双击 EXE 时
    由 Socket 服务器接收 WAKEUP 唤醒窗口，近乎瞬间响应。
"""

import sys
import socket
import os

# 单例检测端口（与 socket 服务器保持一致）
PORT = 24567


def try_send_to_running_instance() -> bool:
    """尝试将命令行参数（文件路径或 WAKEUP 信号）发送给已运行的实例。

    在导入任何重型库之前调用，保证第二次打开时无需等待 Python/Flet 初始化。

    Returns:
        True 表示已有实例在运行（当前进程应直接退出）；
        False 表示没有实例在运行（当前进程应继续启动）。
    """
    filepath = ""
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        if not os.path.isabs(filepath):
            filepath = os.path.abspath(filepath)

    # 没有传入文件路径时，发送 WAKEUP 信号唤醒已有实例显示窗口
    if not filepath:
        filepath = "WAKEUP"

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.1)  # 快速超时，不阻塞冷启动
            s.connect(("127.0.0.1", PORT))
            s.sendall(filepath.encode("utf-8"))
        return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False


# ── 单例快速检测（必须在 import flet 之前执行）──────────────────────────────
# 若已有实例，直接退出，实现"秒唤醒"效果
if try_send_to_running_instance():
    sys.exit(0)

# ── 无已有实例，继续正常启动 ─────────────────────────────────────────────────
import threading
import flet as ft
from viewer import start_ui


def start_single_instance_server(app_instance) -> None:
    """启动后台 Socket 服务端，监听后续启动发来的文件路径或唤醒信号。

    每个连接在独立线程中处理，不阻塞主 UI 线程。

    Args:
        app_instance: LivpViewerApp 实例，用于调用 show_window / _open_file_by_path。
    """

    def handle_client(conn: socket.socket) -> None:
        """处理单个 Socket 客户端连接，解析消息并分发到应用实例。

        Args:
            conn: 已接受的客户端连接对象。
        """
        with conn:
            try:
                data = conn.recv(4096)
                if not data:
                    return
                message = data.decode("utf-8")
                if message == "WAKEUP":
                    # 收到唤醒信号，恢复窗口显示
                    app_instance.show_window()
                elif message:
                    # 收到文件路径，发给事件循环异步处理打开，并随后显示窗口
                    async def _open_and_show():
                        await app_instance._open_file_by_path(message)
                        app_instance.show_window()
                    app_instance.page.run_task(_open_and_show)
            except Exception as e:
                print(f"处理客户端连接异常: {e}")

    def serve() -> None:
        """在独立线程中运行 Socket 服务器主循环，持续接受新连接。"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", PORT))
            s.listen(5)
            while True:
                try:
                    conn, _ = s.accept()
                    threading.Thread(
                        target=handle_client,
                        args=(conn,),
                        daemon=True,
                    ).start()
                except Exception:
                    pass

    threading.Thread(target=serve, daemon=True).start()


def main(page: ft.Page) -> None:
    """Flet 应用主函数，由 ft.app() 调用，负责初始化页面。

    启动流程：
    1. 先将窗口设为不可见，避免初始化期间的白屏闪烁。
    2. 拦截关闭事件（prevent_close），关闭时改为隐藏窗口而非退出进程。
    3. 创建 UI 并启动单例 Socket 服务器。
    4. 初始化完成后将窗口设为可见，实现"成品直接呈现"的效果。

    Args:
        page: Flet 页面对象，由框架自动传入。
    """
    # 步骤 1：先隐藏窗口，避免初始化时出现空白/黑屏窗口
    page.window.visible = False
    page.update()

    # 步骤 2：拦截关闭按钮，改由 app.hide_window 处理（隐藏而非退出）
    page.window.prevent_close = True

    # 步骤 3：初始化 UI 和单例服务器
    app = start_ui(page)
    start_single_instance_server(app)

    # 步骤 4：绑定窗口关闭事件
    # Flet 0.80.5 中必须用 page.window.on_event 在顶层准确拦截关闭操作
    def on_window_event(e):
        # 兼容处理：Flet 0.80.x 使用 e.type 枚举，旧版 Flet 才可能产生 e.data == "close"
        event_type = getattr(e, "type", None)
        if event_type == ft.WindowEventType.CLOSE or e.data == "close":
            app.hide_window()

    page.window.on_event = on_window_event

    # 步骤 5：初始化完毕，显示窗口
    page.window.visible = True
    page.update()



if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
