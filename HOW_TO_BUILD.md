# Livp Viewer 跨平台打包指南

本项目已完全基于 [Flet](https://flet.dev/) 实现，UI 框架天然跨平台。
请严格使用 `uv` 维护依赖。

## 1. 运行开发环境（支持热重载）
开发时推荐运行以下命令，只要你保存 `*.py` 源码，界面会瞬间自动重启以应用变更：
```bash
uv run dev.py
```
若不需要热重载，只作普通启动，请运行：
```bash
uv run main.py
```

## 2. 打包 Windows (.exe)

**前置要求**：
- Windows 系统
- 需要 `uv` 环境安装好所有依赖。
- 安装 Microsoft C++ Build Tools：https://aka.ms/vs/stable/vs_BuildTools.exe
- 安装 Visual C++ Redistributable：https://aka.ms/vc14/vc_redist.x64.exe
- 将C:\Windows\System32\vcruntime140_1.dll复制到C:\Windows\SysWOW64\vcruntime140_1.dll

**操作步骤**：
在项目根目录 `d:\Python\livp_viewer\` 执行以下命令：
```bash
uv run flet build windows
```
**产物位置**：打好的免安装独立包会在 `build/windows/` 目录下生成。

### 设置 .livp 文件关联

打包完成后，可以将 `.livp` 文件与 `LivpViewer.exe` 关联，双击即可直接打开：

**方法一：手动关联**
1. 右键任意 `.livp` 文件 → 打开方式 → 选择其他应用
2. 浏览到打包产物目录中的 `LivpViewer.exe`
3. 勾选"始终使用此应用打开 .livp 文件"

**方法二：通过注册表（管理员权限）**
```bat
:: 注册文件类型
reg add "HKCU\Software\Classes\.livp" /ve /d "LivpViewer.File" /f
reg add "HKCU\Software\Classes\LivpViewer.File\shell\open\command" /ve /d "\"%EXE_PATH%\" \"%%1\"" /f
```
将 `%EXE_PATH%` 替换为 `LivpViewer.exe` 的实际绝对路径。

> 程序已内置命令行参数支持：`LivpViewer.exe "D:\path\to\photo.livp"` 可直接打开指定文件。

## 3. 打包 Android (.apk)

**前置要求极其重要**：
Flet 官方打包 Android 需要极其完备的本地工具链。如果你的系统尚未安装，极易报错。
必须满足：
1. **Flutter SDK**：已安装并加入系统环境变量 `PATH`。可通过 `flutter doctor` 检查。
2. **Android Studio & Android SDK**：确保安装了最新的 Android SDK Platform-Tools 和 Build-Tools。
3. **Java JDK**：通常采用 JDK 11 或 JDK 17，并配置好 `JAVA_HOME`。

**操作步骤**：
当以上环境校验通过后，在项目根目录执行：
```bash
uv run flet build apk
```
**产物位置**：打好的安装包通常输出至 `build/apk/`。

---
> 若在后续打包 APK 时遇到因系统环境变量或 Flutter 依赖导致的报错，请单独搜索该报错处理环境问题，Flet 层面的 Python 代码已经实现了完美的读写隔离与抽象兼容。
