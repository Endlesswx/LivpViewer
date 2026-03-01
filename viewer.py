"""
viewer.py
职责：Livp Viewer 的主界面与交互逻辑。
包含 LivpViewerApp 类，负责 UI 布局、媒体展示（图片/视频）、
播放控制（上一张/下一张/播放/循环）、文件打开及配置持久化等功能。
"""

import asyncio
import subprocess
import sys
import threading
import time
from pathlib import Path

import flet as ft

from config import load_config, save_config
from parser import Playlist


class LivpViewerApp:
    """Livp 文件查看器应用主类，管理 UI 和用户交互。"""

    def __init__(self, page: ft.Page):
        """初始化应用界面和所有 UI 组件，加载用户配置。"""
        self.page = page
        self.page.title = "Livp Viewer"
        self.page.window.icon = "LivpViewer.ico"
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
            visible=True,
        )

        self.grid_view = ft.GridView(
            expand=True,
            max_extent=200,
            child_aspect_ratio=1.0,
            spacing=10,
            run_spacing=10,
            padding=ft.padding.only(right=12),
        )
        self.loading_progress = ft.ProgressBar(value=0, color="amber", bgcolor="#eeeeee", expand=True)
        self.loading_text = ft.Text("0 / 0", width=80, text_align=ft.TextAlign.RIGHT)
        self.loading_row = ft.Row([self.loading_progress, self.loading_text], visible=False)

        # 分页组件 (Pagination)
        self._current_page_index = 0
        self._items_per_page = 45 # 适合各种网格大小并且对 DOM 不再有压力
        
        self.btn_page_prev = ft.ElevatedButton("上一页", on_click=self._on_page_prev_click)
        self.btn_page_next = ft.ElevatedButton("下一页", on_click=self._on_page_next_click)
        self.text_page_info = ft.Text("第 1 / 1 页", size=14, weight=ft.FontWeight.BOLD)
        
        self.pagination_row = ft.Row(
            controls=[
                self.btn_page_prev,
                self.text_page_info,
                self.btn_page_next,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            visible=False,
        )

        self.grid_container = ft.Container(
            expand=True,
            bgcolor="black",
            visible=False,
            padding=ft.padding.only(left=10, top=10, bottom=10, right=0),
            content=ft.Column(
                controls=[
                    self.loading_row,
                    ft.Container(
                        content=self.grid_view,
                        expand=True,
                        theme=ft.Theme(
                            scrollbar_theme=ft.ScrollbarTheme(
                                track_visibility=True,
                                track_color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
                                thumb_visibility=True,
                                thumb_color=ft.Colors.with_opacity(0.5, ft.Colors.WHITE),
                                thickness=6,
                                radius=10,
                                cross_axis_margin=2,
                                main_axis_margin=2,
                            )
                        )
                    ),
                    ft.Container(height=10),
                    self.pagination_row,
                ],
                expand=True,
            )
        )
        
        # 列表异步加载的中断标志
        self._cancel_grid_load = False

        # 废弃原先按全列表缓存比对的机制，仅作为数据检查源
        self._last_loaded_playlist = []

        # 状态文案（点击文件名可复制到剪贴板）
        self.status_text = ft.Text(
            "",
            size=16,
            color="grey400",
            width=200,
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
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
        # 序号文本：显示"当前序号 / 总数量"
        self.index_text = ft.Text(
            "",
            size=14,
            color="grey400",
            text_align=ft.TextAlign.CENTER,
            width=60,
        )
        self.btn_open = ft.ElevatedButton(
            "打开文件", on_click=self.on_btn_open_click
        )
        self.btn_open_location = ft.TextButton(
            "打开图片位置", on_click=self.on_open_location_click, disabled=True
        )
        # 查看列表按钮：用 content 包载 Text 控件以支持动态修改文案
        self._btn_view_all_label = ft.Text("查看列表")
        self.btn_view_all = ft.TextButton(
            content=self._btn_view_all_label,
            on_click=self.on_view_all_click,
            disabled=True,
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
                        [self.btn_prev, self.index_text, self.btn_play, self.btn_next],
                        alignment="center",
                    ),
                    ft.Row(
                        [
                            ft.Row([self.switch_auto_play, ft.Text("自动播放视频")]),
                            ft.Row([self.switch_loop, ft.Text("循环播放")]),
                            self.btn_view_all,
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
                            self.grid_container,
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

        # 全局启动一次系统托盘图标
        self._init_tray_icon()

        # 检查命令行参数（支持打包 EXE 后双击 .livp 文件关联打开）
        self._handle_cli_args()

    def _init_tray_icon(self):
        """初始化完整的系统托盘图标并驻留后台。生命周期跟随主进程。"""
        def run_tray():
            import pystray
            from PIL import Image, ImageDraw

            # 确保不会重复运行
            if hasattr(self, "tray_icon") and self.tray_icon is not None:
                try:
                    self.tray_icon.stop()
                except Exception:
                    pass

            def create_image():
                # 优先尝试从 Flet 包内或者本地资源读取真实的窗口图标
                try:
                    import flet
                    from pathlib import Path
                    
                    # 1. 如果用户提供了自定义的 assets/LivpViewer.ico
                    user_icon = Path("assets/LivpViewer.ico")
                    if user_icon.exists():
                        return Image.open(str(user_icon))
                    
                    # 2. 尝试获取 flet 默认应用图标（与窗口左上角一致）
                    flet_dir = Path(flet.__file__).parent
                    # flet 包内部结构通常在 server 子目录或 bin 里有默认图标
                    possible_paths = [
                        flet_dir / "bin" / "flet" / "assets" / "favicon.png",
                        flet_dir / "assets" / "favicon.png",
                        flet_dir / "bin" / "assets" / "favicon.png"
                    ]
                    for path in possible_paths:
                        if path.exists():
                            return Image.open(str(path))
                except Exception:
                    pass
                
                # 3. 降级：绘制一个简单的纯色图标来代表 Livp Viewer
                image = Image.new('RGB', (64, 64), color=(30, 30, 30))
                d = ImageDraw.Draw(image)
                d.rectangle([16, 16, 48, 48], fill=(64, 150, 255))
                return image

            def on_show(icon, item):
                # 必须利用 Flet 线程分发机制调度到主线程执行前置操作
                self.show_window()

            def on_exit(icon, item):
                icon.stop()
                import os
                # 直接终结进程
                os._exit(0)

            menu = pystray.Menu(
                pystray.MenuItem("显示/隐藏窗口", action=on_show, default=True),
                pystray.MenuItem("完全退出", action=on_exit)
            )
            self.tray_icon = pystray.Icon("LivpViewer", create_image(), "Livp Viewer", menu)
            self.tray_icon.run()

        # 需要在后台守护线程运行
        threading.Thread(target=run_tray, daemon=True).start()

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
        """异步检查命令行参数，在 UI 渲染完成后加载文件，避免阻塞窗口显示。

        支持打包为 EXE 后，将 .livp 文件与 EXE 关联，双击 .livp 文件时
        Windows 会将文件路径作为第一个命令行参数传入。
        若没有命令行参数，则尝试恢复上次打开的文件。

        使用 page.run_task 将文件解析推迟到事件循环中执行，
        确保 UI 先完整渲染，用户可立即看到界面，再进行 IO 密集型的解压操作。
        """
        async def _load_async():
            """在事件循环中延迟执行文件加载，避免阻塞 UI 初始渲染。"""
            for arg in sys.argv[1:]:
                if arg.lower().endswith(".livp") and Path(arg).exists():
                    success = await asyncio.to_thread(self.playlist.load_from_file, arg)
                    if success:
                        await self.load_media_to_ui()
                    return

            # 没有命令行参数，尝试恢复上次打开的文件
            last_file = self._user_config.get("last_file", "")
            if last_file and Path(last_file).exists():
                success = await asyncio.to_thread(self.playlist.load_from_file, last_file)
                if success:
                    await self.load_media_to_ui()

        self.page.run_task(_load_async)

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

    async def load_media_to_ui(self):
        """根据播放列表当前指针，将对应的图片或视频加载到 UI 中展示。"""
        self.media_container.visible = True
        self.grid_container.visible = False
        
        # 核心修复 1：离开列表视图时，立即清空单页的 DOM 树
        if len(self.grid_view.controls) > 0:
             self.grid_view.controls.clear()
             
        self.loading_row.visible = False
        self.pagination_row.visible = False

        self._btn_view_all_label.value = "查看列表"

        livp_path = self.playlist.get_current_live_photo_path()

        # 根据列表游标位置更新上/下翻页按钮及序号文本
        total = len(self.playlist.files)
        self.btn_prev.disabled = self.playlist.current_index <= 0
        self.btn_next.disabled = self.playlist.current_index >= total - 1
        self.btn_view_all.disabled = total == 0
        self.index_text.value = f"{self.playlist.current_index + 1} / {total}" if total > 0 else ""

        if not livp_path:
            self.status_text.value = "没有找到或加载失败 .livp 文件"
            self.media_container.content = self._welcome_view
            self.btn_play.disabled = True
            self.btn_open_location.disabled = True
            self.page.update()
            return

        filename = Path(livp_path).name
        self.status_text.value = f"{filename}"
        self.btn_play.disabled = False
        self.btn_open_location.disabled = False

        # 记住当前文件路径，下次启动时自动恢复
        self._save_current_config()

        if self.switch_auto_play.value:
            # 用户要求打开时直接播放视频
            await self.switch_to_video(autoplay=True)
        else:
            # 默认显示静态图片
            await self.switch_to_image()

    async def switch_to_image(self):
        """从当前 .livp 文件提取静态图片并展示在媒体区域。"""
        livp_path = self.playlist.get_current_live_photo_path()
        if not livp_path:
            return
        self.status_text.value = "正在解析图片..."
        self.status_text.update() # 局部快速刷新，避免 page.update 卡顿
        
        # 核心修复 2：将耗时的读取解压剥离到线程池，释放主线程的 asyncio 轮询，保证 UI 不冻结
        img_path = await asyncio.to_thread(self.playlist.parser.extract_image, livp_path)
        
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
        self.status_text.value = f"{filename}"
        self.page.update()

    async def switch_to_video(self, autoplay=False):
        """从当前 .livp 文件提取视频并在媒体区域播放。

        根据循环播放开关的状态，使用 PlaylistMode.SINGLE（单曲循环）
        或 PlaylistMode.NONE（播完停止并切回静态图）。
        """
        livp_path = self.playlist.get_current_live_photo_path()
        if not livp_path:
            return
        self.status_text.value = "正在解析视频..."
        self.status_text.update()
        
        vid_path = await asyncio.to_thread(self.playlist.parser.extract_video, livp_path)
        
        if not vid_path:
            self.status_text.value = "解析视频失败"
            self.page.update()
            return

        # 延迟导入 flet_video 以加速程序冷启动
        import flet_video as ftv

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
        self.status_text.value = f"{filename}"
        self.page.update()

    def _on_video_complete(self, e):
        """视频播放完毕的回调：在非循环模式下自动切换回静态图片。"""
        if hasattr(self, '_video_start_time') and time.time() - self._video_start_time < 0.5:
            # 忽略刚加载时因底层播放器时长未就绪而瞬间触发的虚假 complete 事件
            return
        self.page.run_task(self.switch_to_image)

    async def _open_file_by_path(self, file_path: str):
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

        success = await asyncio.to_thread(self.playlist.load_from_file, str(resolved))
        if success:
            await self.load_media_to_ui()
        else:
            self.status_text.value = "加载文件失败"
            self.status_text.update()

    # --- 事件响应 ---

    async def on_view_all_click(self, e):
        """处理“查看列表”按钮点击：在媒体视图和列表模式之间切换。"""
        if self.grid_container.visible:
            # 如果当前是列表模式，中断可能正在进行的加载并切换回媒体模式
            self._cancel_grid_load = True
            
            self._btn_view_all_label.value = "查看列表"
            # 从列表页退出，重新加载并刷新媒体状态（利用它恢复已禁用的按钮）
            await self.load_media_to_ui()
        else:
            # 如果当前是媒体模式，构建并显示网格视图
            self._cancel_grid_load = False
            self.page.run_task(self._build_and_show_gridview_async)

    async def _build_and_show_gridview_async(self):
        """异步构建缩略图分页网格视图。使用分页限制 DOM 树的大小，杜绝卡顿。"""
        self.media_container.visible = False
        self.grid_container.visible = True
        self._btn_view_all_label.value = "关闭列表"
        
        # 列表界面不需要单焦点交互，置灰无意义按钮，并修改状态栏
        self.btn_prev.disabled = True
        self.btn_next.disabled = True
        self.btn_play.disabled = True
        self.btn_open_location.disabled = True
        total = len(self.playlist.files)
        self.status_text.value = f"共 {total} 张照片"

        if self._last_loaded_playlist != self.playlist.files:
            self._last_loaded_playlist = self.playlist.files.copy()
            # 跳转到当前正在播放的任务所在的分页
            if total > 0:
                self._current_page_index = self.playlist.current_index // self._items_per_page
            else:
                self._current_page_index = 0

        await self._load_current_page()

    async def _load_current_page(self):
        """加载当前切片页的缩略图到 DOM"""
        total = len(self.playlist.files)
        if total == 0:
            self.grid_view.controls.clear()
            self.pagination_row.visible = False
            self.page.update()
            return

        total_pages = (total + self._items_per_page - 1) // self._items_per_page
        
        # 安全修正边界
        if self._current_page_index >= total_pages:
            self._current_page_index = max(0, total_pages - 1)
        elif self._current_page_index < 0:
            self._current_page_index = 0

        start_idx = self._current_page_index * self._items_per_page
        end_idx = min(start_idx + self._items_per_page, total)
        current_page_files = self.playlist.files[start_idx:end_idx]

        # 更新分页控件
        self.text_page_info.value = f"第 {self._current_page_index + 1} / {total_pages} 页"
        self.btn_page_prev.disabled = (self._current_page_index <= 0)
        self.btn_page_next.disabled = (self._current_page_index >= total_pages - 1)
        self.pagination_row.visible = True

        self.grid_view.controls.clear()
        
        self.loading_row.visible = True
        self.loading_progress.value = 0
        self.loading_text.value = f"0 / {len(current_page_files)}"

        def make_click_handler(idx):
            """生成点击缩略图跳转到对应文件的回调函数。"""
            async def _handle_click(e):
                self._cancel_grid_load = True
                self.playlist.current_index = idx
                await self.load_media_to_ui()
            return _handle_click

        placeholders = []
        for i in range(len(current_page_files)):
            global_idx = start_idx + i
            card = ft.GestureDetector(
                content=ft.Stack(
                    controls=[
                        ft.Container(bgcolor="grey900", border_radius=8),
                        ft.Text(f"{global_idx + 1}", size=12, color="white", weight=ft.FontWeight.BOLD, right=4, top=4)
                    ],
                    expand=True,
                ),
                on_tap=make_click_handler(global_idx),
            )
            placeholders.append(card)
            
        self.grid_view.controls.extend(placeholders)
        self.page.update() # 这一步渲染极为迅速，因为最多只有 45 个骨架屏！

        # --- 阶段 2：后台真正加载替换 ---
        BATCH_SIZE = 15 # 控制并发和刷新频率
        page_total = len(current_page_files)
        
        for batch_start_local in range(0, page_total, BATCH_SIZE):
            if self._cancel_grid_load:
                break
                
            batch_end_local = min(batch_start_local + BATCH_SIZE, page_total)
            batch_files = current_page_files[batch_start_local:batch_end_local]
            
            for local_i, file_path_obj in enumerate(batch_files):
                if self._cancel_grid_load:
                    break
                    
                target_i = batch_start_local + local_i
                
                img_b64 = await asyncio.to_thread(
                    self.playlist.parser.extract_single_thumbnail, 
                    file_path_obj
                )

                if self._cancel_grid_load:
                    break
                
                if img_b64:
                    thumbnail = ft.Image(src=f"data:image/jpeg;base64,{img_b64}", fit="cover", border_radius=8)
                else:
                    thumbnail = ft.Icon(ft.Icons.BROKEN_IMAGE, color="grey500")

                stack_control = self.grid_view.controls[target_i].content
                stack_control.controls[0] = thumbnail
                self.grid_view.controls[target_i].update()

            self.loading_progress.value = batch_end_local / page_total
            self.loading_text.value = f"{batch_end_local} / {page_total}"
            self.loading_row.update()
            
            await asyncio.sleep(0.01)

        self.loading_row.visible = False
        self.page.update()

    async def _on_page_prev_click(self, e):
        """列表上一页"""
        self._cancel_grid_load = True
        self._current_page_index -= 1
        self._cancel_grid_load = False
        self.page.run_task(self._load_current_page)

    async def _on_page_next_click(self, e):
        """列表下一页"""
        self._cancel_grid_load = True
        self._current_page_index += 1
        self._cancel_grid_load = False
        self.page.run_task(self._load_current_page)

    async def _on_media_tap(self, e):
        """左键单击媒体区域：视频模式切换播放/暂停，图片模式开始播放视频。"""
        if self._is_video_mode and self._current_video:
            await self._current_video.play_or_pause()
        else:
            await self.switch_to_video(autoplay=True)

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

    async def _on_path_submit(self, e):
        """处理路径输入框回车提交：根据输入的路径打开文件。"""
        if e.control.value:
            await self._open_file_by_path(e.control.value)

    def _on_config_changed(self, e):
        """处理配置开关变更：保存当前配置到 INI 文件。"""
        self._save_current_config()

    async def _on_loop_and_config_changed(self, e):
        """处理循环播放开关变更：保存配置并实时更新播放模式。"""
        self._save_current_config()
        if self._is_video_mode:
            # 正在播放视频时切换了循环开关，重新加载视频以应用新的播放模式
            await self.switch_to_video(autoplay=True)

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
                    await self._open_file_by_path(picked_path)
        except Exception as ex:
            self.status_text.value = f"打开文件失败: {ex}"
            self.page.update()

    async def on_prev_click(self, e):
        """处理"上一张"按钮点击：切换到播放列表中的前一个文件。"""
        if self.playlist.prev():
            await self.load_media_to_ui()

    async def on_next_click(self, e):
        """处理"下一张"按钮点击：切换到播放列表中的后一个文件。"""
        if self.playlist.next():
            await self.load_media_to_ui()

    async def on_play_click(self, e):
        """处理"播放视频/查看图片"按钮点击：在图片和视频模式之间切换。"""
        if self._is_video_mode:
            # 当前正在播放视频，切换回静态图片
            await self.switch_to_image()
        else:
            # 当前显示静态图片，切换到视频播放
            await self.switch_to_video(autoplay=True)

    def on_open_location_click(self, e):
        """处理"打开图片位置"按钮点击：在 Windows 资源管理器中定位到原始文件。"""
        livp_path = self.playlist.get_current_live_photo_path()
        if not livp_path:
            return
        subprocess.Popen(["explorer", "/select,", str(Path(livp_path))])

    def hide_window(self) -> None:
        """保存配置后将窗口隐藏，进程继续在后台驻留。

        不退出进程，由 main.py 的 Socket WAKEUP 信号瞬间恢复窗口，
        实现"第二次打开秒显示"的效果。
        """
        self._cancel_grid_load = True
        
        # 核心修复 1 关联位置：窗口收起后台时，彻底卸载列表大内存组件
        if len(self.grid_view.controls) > 0:
            self.grid_view.controls.clear()
            
        self._save_current_config()
        self.page.window.visible = False
        self.page.update()

    def show_window(self) -> None:
        """将隐藏在后台的窗口重新显示并置于前台。
        如果是托盘图标的"显示/隐藏"菜单点击触发，则进行反转；被唤醒或加载文件时直接显示。

        由 main.py 的 Socket 服务端在收到 WAKEUP 信号或文件路径时调用，
        实现"再次打开近乎瞬间显示窗口"的效果。
        """
        # 利用 Flet 的异步调度器，避免系统托盘的外部线程更新 UI 导致假死
        async def _safe_show():
            if self.page.window.visible:
                # 已经显示时，则主动隐藏（多用于托盘双击/点击）
                self.hide_window()
                return

            # 不可见时，恢复窗口显示，并确保不要被最小化截断
            self.page.window.minimized = False
            self.page.window.visible = True
            
            # 使用同步方法抢占前台焦点
            self.page.window.always_on_top = True
            self.page.update()
            
            self.page.window.always_on_top = False
            self.page.update()

        # Flet 线程分发机制，把操作推到事件循环，跨线程也安全
        self.page.run_task(_safe_show)

    def on_close(self, e):
        """应用关闭时保存配置并清理临时缓存文件。"""
        self._cancel_grid_load = True
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
