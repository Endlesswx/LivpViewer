"""
viewer.py
职责：Livp Viewer 的主界面与交互逻辑。
包含 LivpViewerApp 类，负责 UI 布局、媒体展示（图片/视频）、
播放控制（上一张/下一张/播放/循环）、文件打开及配置持久化等功能。
"""

import subprocess
import sys
import threading
import time
from pathlib import Path

import flet as ft
import flet_video as ftv

from config import load_config, save_config
from parser import Playlist


class LivpViewerApp:
    """Livp 文件查看器应用主类，管理 UI 和用户交互。"""

    def __init__(self, page: ft.Page):
        """初始化应用界面和所有 UI 组件，加载用户配置。"""
        self.page = page
        self.page.title = "Livp Viewer"
        self.page.theme_mode = "dark"
        self.page.padding = 0

        # 播放列表控制器
        self.playlist = Playlist()

        # 加载用户配置
        self._user_config = load_config()

        # 媒体交互状态
        self._is_video_mode = False
        self._current_video = None

        # 文件选择器
        self.file_picker = ft.FilePicker()

        # === UI 组件 ===
        self.media_container = ft.Container(
            expand=True,
            bgcolor="black",
            alignment=ft.Alignment(0, 0),
        )

        # 状态文案（点击文件名可复制到剪贴板）
        self.status_text = ft.Text("", size=16, color="grey400")
        self.status_text_wrapper = ft.GestureDetector(
            content=self.status_text,
            on_tap=self._on_filename_click,
        )

        # 路径输入框（替代拖放功能，用户可粘贴文件路径）
        self.path_input = ft.TextField(
            hint_text="将 .livp 文件路径粘贴到此处，按回车打开",
            on_submit=self._on_path_submit,
            expand=True,
            border_color="grey600",
            text_size=14,
        )

        # 初始欢迎界面：路径输入框 + 打开按钮
        self._welcome_view = ft.Column(
            alignment="center",
            horizontal_alignment="center",
            expand=True,
            controls=[
                ft.Icon(ft.Icons.PHOTO_LIBRARY, size=64, color="grey500"),
                ft.Text("打开或粘贴 .livp 文件路径", size=18, color="grey400"),
                ft.Container(
                    width=500,
                    content=ft.Row(
                        controls=[
                            self.path_input,
                            ft.ElevatedButton(
                                "浏览...",
                                on_click=self.on_btn_open_click,
                            ),
                        ]
                    ),
                ),
            ],
        )

        # 控制栏按钮
        self.btn_prev = ft.TextButton(
            "上一张", on_click=self.on_prev_click, disabled=True
        )
        self.btn_play = ft.ElevatedButton(
            "播放视频", on_click=self.on_play_click, disabled=True
        )
        self.btn_next = ft.TextButton(
            "下一张", on_click=self.on_next_click, disabled=True
        )
        self.btn_open = ft.ElevatedButton(
            "打开文件", on_click=self.on_btn_open_click
        )
        self.btn_open_location = ft.TextButton(
            "打开图片位置", on_click=self.on_open_location_click, disabled=True
        )

        # 开关（从配置恢复状态）
        self.switch_auto_play = ft.Switch(
            value=self._user_config.get("auto_play") == "true",
            on_change=self._on_config_changed,
        )
        self.switch_loop = ft.Switch(
            value=self._user_config.get("loop") == "true",
            on_change=self._on_loop_and_config_changed,
        )

        # 布局拼装
        control_bar = ft.Container(
            padding=10,
            bgcolor="surfaceVariant",
            content=ft.Row(
                alignment="spaceBetween",
                controls=[
                    ft.Row([self.btn_open, self.btn_open_location, self.status_text_wrapper]),
                    ft.Row(
                        [self.btn_prev, self.btn_play, self.btn_next],
                        alignment="center",
                    ),
                    ft.Row(
                        [
                            ft.Row([self.switch_auto_play, ft.Text("自动播放视频")]),
                            ft.Row([self.switch_loop, ft.Text("循环播放")]),
                        ]
                    ),
                ],
            ),
        )

        # 复制成功提示（显示在左上角）
        self._toast_text = ft.Text("", color="white", size=14)
        self._toast = ft.Container(
            content=self._toast_text,
            bgcolor=ft.Colors.with_opacity(0.8, "black"),
            padding=ft.Padding(12, 8, 12, 8),
            border_radius=8,
            visible=False,
        )

        # 默认显示欢迎界面
        self.media_container.content = self._welcome_view

        self.page.add(
            ft.Stack(
                controls=[
                    ft.Column(
                        controls=[
                            self.media_container,
                            control_bar,
                        ],
                        expand=True,
                        spacing=0,
                    ),
                    ft.Container(
                        content=self._toast,
                        alignment=ft.Alignment(-1, -1),
                        padding=ft.Padding(16, 16, 0, 0),
                        ignore_interactions=True,
                    ),
                ],
                expand=True,
            )
        )

        # 释放系统资源的时机
        self.page.on_close = self.on_close

        # 检查命令行参数（支持打包 EXE 后双击 .livp 文件关联打开）
        self._handle_cli_args()

    def _show_toast(self, message: str, duration: float = 2.0):
        """在界面左上角显示一条短暂提示消息，duration 秒后自动消失。

        Args:
            message: 要显示的提示文字。
            duration: 显示时长（秒），默认 2 秒。
        """
        self._toast_text.value = message
        self._toast.visible = True
        self.page.update()

        def _hide():
            """延时隐藏提示。"""
            self._toast.visible = False
            self.page.update()

        timer = threading.Timer(duration, _hide)
        timer.daemon = True
        timer.start()

    def _handle_cli_args(self):
        """检查命令行参数，如果传入了 .livp 文件路径则自动打开。

        支持打包为 EXE 后，将 .livp 文件与 EXE 关联，双击 .livp 文件时
        Windows 会将文件路径作为第一个命令行参数传入。
        若没有命令行参数，则尝试恢复上次打开的文件。
        """
        for arg in sys.argv[1:]:
            if arg.lower().endswith(".livp") and Path(arg).exists():
                success = self.playlist.load_from_file(arg)
                if success:
                    self.load_media_to_ui()
                return

        # 没有命令行参数，尝试恢复上次打开的文件
        last_file = self._user_config.get("last_file", "")
        if last_file and Path(last_file).exists():
            success = self.playlist.load_from_file(last_file)
            if success:
                self.load_media_to_ui()

    def _save_current_config(self):
        """将当前开关状态和最后打开的文件路径保存到 INI 配置文件。"""
        settings = {
            "auto_play": str(self.switch_auto_play.value).lower(),
            "loop": str(self.switch_loop.value).lower(),
            "last_file": self.playlist.get_current_live_photo_path(),
        }
        save_config(settings)

    def _wrap_with_gesture(self, content):
        """将媒体内容包裹在手势检测器中，使其支持左键/右键/拖动操作。

        子控件（如视频原生控制栏）优先接收事件，未处理的事件冒泡到手势检测器。
        """
        return ft.GestureDetector(
            content=content,
            on_tap=self._on_media_tap,
            on_secondary_tap=self._on_media_right_click,
            on_pan_start=self._on_media_pan_start,
            expand=True,
        )

    def load_media_to_ui(self):
        """根据播放列表当前指针，将对应的图片或视频加载到 UI 中展示。"""
        livp_path = self.playlist.get_current_live_photo_path()

        # 根据列表游标位置更新上/下翻页按钮的可用状态
        self.btn_prev.disabled = self.playlist.current_index <= 0
        self.btn_next.disabled = (
            self.playlist.current_index >= len(self.playlist.files) - 1
        )

        if not livp_path:
            self.status_text.value = "没有找到或加载失败 .livp 文件"
            self.media_container.content = self._welcome_view
            self.btn_play.disabled = True
            self.btn_open_location.disabled = True
            self.page.update()
            return

        filename = Path(livp_path).name
        self.status_text.value = f"正在查看: {filename}"
        self.btn_play.disabled = False
        self.btn_open_location.disabled = False

        # 记住当前文件路径，下次启动时自动恢复
        self._save_current_config()

        if self.switch_auto_play.value:
            # 用户要求打开时直接播放视频
            self.switch_to_video(autoplay=True)
        else:
            # 默认显示静态图片
            self.switch_to_image()

    def switch_to_image(self):
        """从当前 .livp 文件提取静态图片并展示在媒体区域。"""
        livp_path = self.playlist.get_current_live_photo_path()
        if not livp_path:
            return
        self.status_text.value = "正在解析图片..."
        self.page.update()
        img_path = self.playlist.parser.extract_image(livp_path)
        if not img_path:
            self.status_text.value = "解析图片失败"
            self.page.update()
            return

        self.media_container.content = self._wrap_with_gesture(
            ft.Image(src=img_path, fit="contain", expand=True)
        )
        self._is_video_mode = False
        self._current_video = None
        self.btn_play.content = "播放视频"
        filename = Path(livp_path).name
        self.status_text.value = f"正在查看: {filename}"
        self.page.update()

    def switch_to_video(self, autoplay=False):
        """从当前 .livp 文件提取视频并在媒体区域播放。

        根据循环播放开关的状态，使用 PlaylistMode.SINGLE（单曲循环）
        或 PlaylistMode.NONE（播完停止并切回静态图）。
        """
        livp_path = self.playlist.get_current_live_photo_path()
        if not livp_path:
            return
        self.status_text.value = "正在解析视频..."
        self.page.update()
        vid_path = self.playlist.parser.extract_video(livp_path)
        if not vid_path:
            self.status_text.value = "解析视频失败"
            self.page.update()
            return

        # 根据循环开关决定播放模式
        if self.switch_loop.value:
            mode = ftv.PlaylistMode.SINGLE
            on_complete_handler = None
        else:
            mode = ftv.PlaylistMode.NONE
            on_complete_handler = self._on_video_complete

        video = ftv.Video(
            playlist=[ftv.VideoMedia(resource=vid_path)],
            autoplay=autoplay,
            playlist_mode=mode,
            expand=True,
            on_complete=on_complete_handler,
        )

        self._video_start_time = time.time()
        self.media_container.content = self._wrap_with_gesture(video)
        self._is_video_mode = True
        self._current_video = video
        self.btn_play.content = "查看图片"
        filename = Path(livp_path).name
        self.status_text.value = f"正在查看: {filename}"
        self.page.update()

    def _on_video_complete(self, e):
        """视频播放完毕的回调：在非循环模式下自动切换回静态图片。"""
        if hasattr(self, '_video_start_time') and time.time() - self._video_start_time < 0.5:
            # 忽略刚加载时因底层播放器时长未就绪而瞬间触发的虚假 complete 事件
            return
        self.switch_to_image()

    def _open_file_by_path(self, file_path: str):
        """根据文件路径加载 .livp 文件并显示到界面。

        Args:
            file_path: .livp 文件的路径字符串。
        """
        resolved = Path(file_path.strip().strip('"').strip("'")).resolve()
        if not resolved.exists():
            self.status_text.value = f"文件不存在: {resolved}"
            self.page.update()
            return
        if resolved.suffix.lower() != ".livp":
            self.status_text.value = "请选择 .livp 格式的文件"
            self.page.update()
            return

        success = self.playlist.load_from_file(str(resolved))
        if success:
            self.load_media_to_ui()
        else:
            self.status_text.value = "加载文件失败"
            self.page.update()

    # --- 事件响应 ---

    async def _on_media_tap(self, e):
        """左键单击媒体区域：视频模式切换播放/暂停，图片模式开始播放视频。"""
        if self._is_video_mode and self._current_video:
            await self._current_video.play_or_pause()
        else:
            self.switch_to_video(autoplay=True)

    def _on_media_right_click(self, e):
        """右键单击媒体区域：切换全屏/非全屏。"""
        self.page.window.full_screen = not self.page.window.full_screen
        self.page.update()

    async def _on_media_pan_start(self, e):
        """拖动媒体区域：非全屏时移动窗口，全屏时忽略。"""
        if not self.page.window.full_screen:
            await self.page.window.start_dragging()

    def _on_filename_click(self, e):
        """处理文件名点击：将当前文件名复制到系统剪贴板。"""
        livp_path = self.playlist.get_current_live_photo_path()
        if not livp_path:
            return
        filename = Path(livp_path).name
        try:
            # 尝试直接使用 Flet 的剪贴板 API
            if hasattr(self.page, "set_clipboard"):
                self.page.set_clipboard(filename)
            else:
                raise AttributeError("Page has no set_clipboard")
        except BaseException:
            # 回退使用 Windows 原生 clip 命令
            subprocess.run("clip", text=True, input=filename, creationflags=subprocess.CREATE_NO_WINDOW)
            
        self._show_toast(f"已复制: {filename}")

    def _on_path_submit(self, e):
        """处理路径输入框回车提交：根据输入的路径打开文件。"""
        if e.control.value:
            self._open_file_by_path(e.control.value)

    def _on_config_changed(self, e):
        """处理配置开关变更：保存当前配置到 INI 文件。"""
        self._save_current_config()

    def _on_loop_and_config_changed(self, e):
        """处理循环播放开关变更：保存配置并实时更新播放模式。"""
        self._save_current_config()
        if self._is_video_mode:
            # 正在播放视频时切换了循环开关，重新加载视频以应用新的播放模式
            self.switch_to_video(autoplay=True)

    async def on_btn_open_click(self, e):
        """处理"打开文件"按钮点击：弹出文件选择对话框选择 .livp 文件。"""
        try:
            files = await self.file_picker.pick_files(
                dialog_title="选择 Livp 文件",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["livp"]
            )
            if files and len(files) > 0:
                picked_path = files[0].path
                if picked_path:
                    self._open_file_by_path(picked_path)
        except Exception as ex:
            self.status_text.value = f"打开文件失败: {ex}"
            self.page.update()

    def on_prev_click(self, e):
        """处理"上一张"按钮点击：切换到播放列表中的前一个文件。"""
        if self.playlist.prev():
            self.load_media_to_ui()

    def on_next_click(self, e):
        """处理"下一张"按钮点击：切换到播放列表中的后一个文件。"""
        if self.playlist.next():
            self.load_media_to_ui()

    def on_play_click(self, e):
        """处理"播放视频/查看图片"按钮点击：在图片和视频模式之间切换。"""
        if self._is_video_mode:
            # 当前正在播放视频，切换回静态图片
            self.switch_to_image()
        else:
            # 当前显示静态图片，切换到视频播放
            self.switch_to_video(autoplay=True)

    def on_open_location_click(self, e):
        """处理"打开图片位置"按钮点击：在 Windows 资源管理器中定位到原始文件。"""
        livp_path = self.playlist.get_current_live_photo_path()
        if not livp_path:
            return
        subprocess.Popen(["explorer", "/select,", str(Path(livp_path))])

    def on_close(self, e):
        """应用关闭时保存配置并清理临时缓存文件。"""
        self._save_current_config()
        self.playlist.cleanup()
        if hasattr(self.page, "window_destroy"):
            self.page.window_destroy()
        elif hasattr(self.page, "window_close"):
            self.page.window_close()
        else:
            raise SystemExit


def start_ui(page: ft.Page):
    """Flet 应用入口函数，创建 LivpViewerApp 实例。"""
    return LivpViewerApp(page)
