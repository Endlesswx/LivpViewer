"""
dev.py
职责：开发模式热重载脚本。
监控项目目录下 .py 文件的变动，检测到修改后自动重启应用，
方便开发调试时无需手动停止和重新启动。
"""

import subprocess
import sys
from pathlib import Path

from watchfiles import watch


def run_app():
    """通过 uv 启动主应用进程并返回 Popen 对象。"""
    print("[Dev] 正在启动应用...")
    return subprocess.Popen(["uv", "run", "main.py"])


def main():
    """开发模式主循环：监控文件变动并自动重启应用。"""
    current_dir = Path(__file__).parent.absolute()

    print(f"[Dev] 监控目录: {current_dir}")
    print("[Dev] 当你保存 .py 文件时程序将自动重启")
    print("[Dev] 按 Ctrl+C 退出开发模式")

    process = run_app()

    try:
        for changes in watch(str(current_dir)):
            has_py_changes = any(
                Path(path).suffix == ".py" for _, path in changes
            )
            if has_py_changes:
                print(f"\n[Dev] 检测到代码变动: {changes}")
                print("[Dev] 杀死旧进程并重启...")
                if process:
                    process.terminate()
                    process.wait(timeout=3)
                process = run_app()
    except KeyboardInterrupt:
        print("\n[Dev] 退出开发模式。")
        if process:
            process.terminate()


if __name__ == "__main__":
    main()
