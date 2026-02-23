# Livp Viewer (Flet)

专为 Apple Live Photo (`.livp`) 打造的极简查看器，基于 Python 与 Flet 开发。

## 特性
- 默认展示 `.livp` 中的高画质静态照片
- 一键切换查看文件中包含的动态视频（`.mov` 或 `.mp4`）
- 扫描同级目录下所有 `.livp` 文件，支持上一张/下一张切换
- 提供自动播放与循环播放开关

## 快速开始
本项目使用 `uv` 作为包管理器。

1. 启动应用（生产模式）
   ```bash
   uv run main.py
   ```

2. 启动应用（开发模式，支持热重载）
   ```bash
   uv run dev.py
   ```

## 打包为可执行程序
完整的本地打包说明见 [HOW_TO_BUILD.md](file:///d:/Python/livp_viewer/HOW_TO_BUILD.md)。

### GitHub Actions 远程打包（免装本地 C++ 工具链）
仓库已提供 Windows 打包流水线：[build-windows.yml](file:///d:/Python/livp_viewer/.github/workflows/build-windows.yml)。

操作步骤：
1. 推送代码到 GitHub
2. 打开 Actions，选择 build-windows 并运行
3. 下载 artifact：windows-exe
