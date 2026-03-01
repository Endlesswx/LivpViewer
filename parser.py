"""
parser.py
职责：处理 .livp 文件的解析、按需解压（图片/视频）、管理临时缓存文件，
以及维护同级目录下所有 .livp 文件的播放列表。
"""

import hashlib
import os
import shutil
import time
import zipfile
import tempfile
from pathlib import Path
from typing import Optional, List
import base64
import io

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

from thumbnail_cache import ThumbnailCache


class LivpParser:
    """处理单个 .livp 文件的物理提取与临时缓存管理。

    .livp 文件本质是 ZIP 包，内含一张静态图片（JPG/HEIC）和一段动态视频（MOV/MP4）。
    本类负责将它们按需解压到临时目录，并在适当时机清理。
    """

    def __init__(self):
        """初始化解析器，创建临时缓存目录和 SQLite 缩略图缓存实例。"""
        self.temp_dir = Path(tempfile.gettempdir()) / "livp_viewer_cache"
        self._ensure_temp_dir()
        # 初始化缩略图单文件缓存 (存放在用户目录或是应用同级，这里放在同级)
        self.thumb_cache = ThumbnailCache()

    def _ensure_temp_dir(self):
        """确保临时缓存目录存在，不存在则创建。"""
        if not self.temp_dir.exists():
            self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _build_cache_path(self, file_path: str, kind: str, ext: str) -> Path:
        file_path_obj = Path(file_path).resolve()
        try:
            mtime = file_path_obj.stat().st_mtime_ns
        except OSError:
            mtime = time.time_ns()
        raw = f"{file_path_obj}:{mtime}"
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        return self.temp_dir / f"{kind}_{digest}{ext}"

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
                        ext = Path(filename).suffix
                        target = self._build_cache_path(file_path, "img", ext)
                        if target.exists():
                            return str(target.absolute())
                        with zf.open(file_info) as source, open(target, "wb") as dest:
                            shutil.copyfileobj(source, dest)
                        return str(target.absolute())
        except Exception as e:
            print(f"Livp IMG 解析异常: {e}")
        return None

    def extract_thumbnail_base64(self, file_path: str) -> Optional[str]:
        """专门用于缩略图列表的高效提取方法。
        
        首先查询 SQLite 单文件缓存，命中则直接返回 base64；
        未命中则从 ZIP 提取图片的二进制流存入缓存，再返回 base64。
        全程不会在硬盘上生成零散的临时图片文件。
        """
        try:
            target_path = Path(file_path).absolute()
            if not target_path.exists():
                return None
            mtime = target_path.stat().st_mtime
            
            # 1. 尝试从缓存直接拿二进制数据
            cached_bytes = self.thumb_cache.get(str(target_path), mtime)
            if cached_bytes:
                return base64.b64encode(cached_bytes).decode('utf-8')
            
            # 2. 缓存未命中，执行昂贵的 ZIP 解包 IO
            with zipfile.ZipFile(str(target_path), "r") as zf:
                for file_info in zf.infolist():
                    filename = file_info.filename.lower()
                    if filename.endswith((".jpg", ".jpeg", ".heic")):
                        with zf.open(file_info) as source:
                            img_bytes = source.read()
                            
                            # 进行微缩采样处理，极大降低缓存体积与 UI 内存压力
                            if PILImage:
                                try:
                                    with PILImage.open(io.BytesIO(img_bytes)) as pil_img:
                                        # 针对 HEIC 格式的特别防御或直接转换 RGB
                                        if pil_img.mode != "RGB":
                                            pil_img = pil_img.convert("RGB")
                                        pil_img.thumbnail((256, 256))
                                        out_buffer = io.BytesIO()
                                        pil_img.save(out_buffer, format="JPEG", quality=75)
                                        img_bytes = out_buffer.getvalue()
                                except Exception as e:
                                    print(f"PIL 图片压缩失败 (可能不支持 HEIC 等)，回退原图缓存: {e}")

                            # 异步塞进缓存（自动处理 LRU 和大小上限）
                            self.thumb_cache.put(str(target_path), mtime, img_bytes)
                            
                            # 转成 Base64 返回给 Flet UI 呈现
                            return base64.b64encode(img_bytes).decode('utf-8')
        except Exception as e:
            print(f"Livp 缩略图提取异常: {e}")
        return None

    def extract_thumbnails_base64_batch(self, file_paths: List[Path]) -> List[Optional[str]]:
        """批量获取缩略图 Base64，充分利用数据库的批量查询。
        
        对于未命中缓存的文件，再进行 ZIP 解压。
        返回结果列表与传入的 file_paths 顺序一一对应。
        """
        results: List[Optional[str]] = [None] * len(file_paths)
        if not file_paths:
            return results

        # 1. 收集物理文件的存在状态与修改时间
        mtimes = {}
        str_paths = []
        valid_indices = []
        for i, path_obj in enumerate(file_paths):
            target_path = path_obj.absolute()
            if target_path.exists():
                str_path = str(target_path)
                mtimes[str_path] = target_path.stat().st_mtime
                str_paths.append(str_path)
                valid_indices.append((i, str_path, target_path))

        if not str_paths:
            return results

        # 2. 批量查询数据库缓存
        cached_data = self.thumb_cache.get_many(str_paths, mtimes)

        # 3. 组装结果，未命中则立即解包提取
        for i, str_path, target_path in valid_indices:
            img_bytes = cached_data.get(str_path)
            
            if img_bytes:
                results[i] = base64.b64encode(img_bytes).decode('utf-8')
            else:
                # 缓存未命中，执行 ZIP 解包
                try:
                    with zipfile.ZipFile(str(target_path), "r") as zf:
                        for file_info in zf.infolist():
                            filename = file_info.filename.lower()
                            if filename.endswith((".jpg", ".jpeg", ".heic")):
                                with zf.open(file_info) as source:
                                    img_bytes = source.read()
                                    
                                    if PILImage:
                                        try:
                                            with PILImage.open(io.BytesIO(img_bytes)) as pil_img:
                                                if pil_img.mode != "RGB":
                                                    pil_img = pil_img.convert("RGB")
                                                pil_img.thumbnail((256, 256))
                                                out_buffer = io.BytesIO()
                                                pil_img.save(out_buffer, format="JPEG", quality=75)
                                                img_bytes = out_buffer.getvalue()
                                        except Exception as e:
                                            print(f"PIL 压缩失败: {e}")

                                    # 单个填充缓存
                                    self.thumb_cache.put(str_path, mtimes[str_path], img_bytes)
                                    results[i] = base64.b64encode(img_bytes).decode('utf-8')
                                break  # 找到图片后跳出当前 zipinfo 循环
                except Exception as e:
                    print(f"Livp 批量缩略图提取解压异常 ({target_path.name}): {e}")
                    
        return results

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
                        ext = Path(filename).suffix
                        target = self._build_cache_path(file_path, "vid", ext)
                        if target.exists():
                            return str(target.absolute())
                        with zf.open(file_info) as source, open(target, "wb") as dest:
                            shutil.copyfileobj(source, dest)
                        return str(target.absolute())
        except Exception as e:
            print(f"Livp VID 解析异常: {e}")
        return None

    def extract_single_thumbnail(self, path_obj: Path) -> Optional[str]:
        """提取单个文件的缩略图（用于提供给外部微批次循环调用以防主线程被大批次耗时阻塞）。"""
        res = self.extract_thumbnails_base64_batch([path_obj])
        return res[0] if res else None

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

        directory = target_path.parent
        try:
            with os.scandir(directory) as it:
                files_with_mtime = [
                    (Path(f.path), f.stat().st_mtime)
                    for f in it
                    if f.is_file() and f.name.lower().endswith(".livp")
                ]
                # 按修改时间倒序排序（最新拍的放在最前面）
                files_with_mtime.sort(key=lambda x: x[1], reverse=True)
                self.files = [f[0] for f in files_with_mtime]
        except OSError:
            self.files = []

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
