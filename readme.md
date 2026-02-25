# Livp Viewer

Windows 桌面端 .livp (Live Photo) 文件查看器，可浏览静态图片并播放内嵌的动态视频。

## 功能

- 打开 .livp 文件，默认展示静态图片，可切换播放视频
- 自动扫描同目录下所有 .livp 文件，支持上一张/下一张切换
- 鼠标左键单击：图片模式下开始播放视频，视频模式下播放/暂停切换
- 鼠标右键单击：切换全屏/窗口模式
- 非全屏时拖动媒体区域可移动窗口
- 点击文件名复制到剪贴板
- 支持自动播放视频、循环播放，设置自动保存
- 单实例运行，双击 .livp 文件秒开（复用已运行实例）
- 支持命令行参数传入文件路径，可关联 .livp 文件类型

## 快速开始

需要 Python 3.12+，使用 [uv](https://docs.astral.sh/uv/) 管理依赖：

```bash
uv run main.py
```

开发模式（文件保存后自动重启）：

```bash
uv run dev.py
```

## 打包

### 本地打包

```bash
uv run flet build windows
```

构建产物在 `build/windows` 目录下。详细说明见 [HOW_TO_BUILD.md](HOW_TO_BUILD.md)。

### GitHub Actions 远程打包

仓库提供 Windows 打包流水线，构建完成后自动创建 GitHub Release：

1. 在 `pyproject.toml` 中更新版本号
2. 推送代码到 GitHub
3. 打开 Actions → build-windows → Run workflow
4. 构建完成后自动发布 Release 并附带打包好的 zip 文件

## 项目结构

| 文件 | 说明 |
|------|------|
| `main.py` | 应用入口，单实例控制 |
| `viewer.py` | 主界面与交互逻辑 |
| `parser.py` | .livp 文件解析、临时缓存管理、播放列表 |
| `config.py` | 用户配置持久化（INI 格式） |
| `dev.py` | 开发模式热重载脚本 |

## 技术栈

- [Flet](https://flet.dev/) — Python 跨平台桌面 UI 框架
- [flet-video](https://pub.dev/packages/flet_video) — 视频播放组件
