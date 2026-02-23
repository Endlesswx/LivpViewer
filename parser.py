"""
parser.py
职责：处理 .livp 文件的解析、按需解压（图片/视频）、管理临时缓存文件，
以及维护同级目录下所有 .livp 文件的播放列表。
"""

import shutil
import time
import zipfile
import tempfile
from pathlib import Path
from typing import Optional, List


class LivpParser:
    """处理单个 .livp 文件的物理提取与临时缓存管理。

    .livp 文件本质是 ZIP 包，内含一张静态图片（JPG/HEIC）和一段动态视频（MOV/MP4）。
    本类负责将它们按需解压到临时目录，并在适当时机清理。
    """

    def __init__(self):
        """初始化解析器，创建临时缓存目录。"""
        self.temp_dir = Path(tempfile.gettempdir()) / "livp_viewer_cache"
        self._ensure_temp_dir()

    def _ensure_temp_dir(self):
        """确保临时缓存目录存在，不存在则创建。"""
        if not self.temp_dir.exists():
            self.temp_dir.mkdir(parents=True, exist_ok=True)

    def purge_all(self):
        """清空整个临时缓存目录，释放磁盘空间后重新创建空目录。"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def extract_image(self, file_path: str) -> Optional[str]:
        """从 .livp 文件中提取静态图片到临时目录。

        文件名带时间戳以避免 Flet 图片缓存导致的不刷新问题。

        Args:
            file_path: .livp 文件的绝对路径。

        Returns:
            提取后的图片文件绝对路径，失败则返回 None。
        """
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                for file_info in zf.infolist():
                    filename = file_info.filename.lower()
                    if filename.endswith((".jpg", ".jpeg", ".heic")):
                        target = (
                            self.temp_dir
                            / f"img_{int(time.time() * 1000)}{Path(filename).suffix}"
                        )
                        with zf.open(file_info) as source, open(
                            target, "wb"
                        ) as dest:
                            shutil.copyfileobj(source, dest)
                        return str(target.absolute())
        except Exception as e:
            print(f"Livp IMG 解析异常: {e}")
        return None

    def extract_video(self, file_path: str) -> Optional[str]:
        """从 .livp 文件中提取视频到临时目录。

        文件名带时间戳以避免缓存冲突。

        Args:
            file_path: .livp 文件的绝对路径。

        Returns:
            提取后的视频文件绝对路径，失败则返回 None。
        """
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                for file_info in zf.infolist():
                    filename = file_info.filename.lower()
                    if filename.endswith((".mov", ".mp4")):
                        target = (
                            self.temp_dir
                            / f"vid_{int(time.time() * 1000)}{Path(filename).suffix}"
                        )
                        with zf.open(file_info) as source, open(
                            target, "wb"
                        ) as dest:
                            shutil.copyfileobj(source, dest)
                        return str(target.absolute())
        except Exception as e:
            print(f"Livp VID 解析异常: {e}")
        return None


class Playlist:
    """管理同级目录下所有 .livp 文件的播放列表。

    从用户选择的文件出发，自动扫描同级目录中的所有 .livp 文件，
    按文件名排序，并提供上一张/下一张的导航功能。
    """

    def __init__(self):
        """初始化空的播放列表和解析器。"""
        self.parser = LivpParser()
        self.files: List[Path] = []
        self.current_index: int = -1

    def load_from_file(self, file_path_str: str) -> bool:
        """从指定文件初始化播放列表，扫描同级目录下所有 .livp 文件。

        每次加载新文件时会清理旧的临时缓存以释放磁盘空间。

        Args:
            file_path_str: 用户选择的 .livp 文件路径。

        Returns:
            加载成功返回 True，文件不存在则返回 False。
        """
        target_path = Path(file_path_str).absolute()
        if not target_path.exists() or not target_path.is_file():
            return False

        # 换文件夹或新文件时，清理旧缓存释放磁盘
        self.parser.purge_all()

        directory = target_path.parent
        self.files = sorted(
            [
                f
                for f in directory.iterdir()
                if f.is_file() and f.suffix.lower() == ".livp"
            ]
        )

        if target_path in self.files:
            self.current_index = self.files.index(target_path)
        else:
            self.files.insert(0, target_path)
            self.current_index = 0

        return True

    def get_current_live_photo_path(self) -> str:
        """获取当前播放列表指针对应的 .livp 文件路径。

        Returns:
            当前文件的绝对路径字符串，列表为空时返回空字符串。
        """
        if not self.files or self.current_index < 0:
            return ""
        return str(self.files[self.current_index])

    def next(self) -> bool:
        """将播放列表指针前进一位。

        Returns:
            成功前进返回 True，已到末尾则返回 False。
        """
        if not self.files:
            return False
        if self.current_index < len(self.files) - 1:
            self.current_index += 1
            return True
        return False

    def prev(self) -> bool:
        """将播放列表指针后退一位。

        Returns:
            成功后退返回 True，已在开头则返回 False。
        """
        if not self.files:
            return False
        if self.current_index > 0:
            self.current_index -= 1
            return True
        return False

    def cleanup(self):
        """清理所有临时缓存文件，通常在应用退出时调用。"""
        self.parser.purge_all()
