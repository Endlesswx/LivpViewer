"""
config.py
职责：管理应用用户配置的持久化存储。
使用 INI 文件格式保存和读取用户偏好设置（如自动播放、循环播放等），
配置文件保存在应用同级目录下的 config.ini 中。
"""

import configparser
from pathlib import Path


# 配置文件路径：与主程序同级目录下的 config.ini
CONFIG_PATH = Path(__file__).parent / "config.ini"

# 默认配置值
DEFAULTS = {
    "auto_play": "false",
    "loop": "false",
}


def load_config() -> dict:
    """从 INI 文件加载用户配置。

    如果配置文件不存在或读取失败，返回默认值。

    Returns:
        包含用户配置的字典，键为配置项名称，值为字符串。
    """
    config = configparser.ConfigParser()
    result = dict(DEFAULTS)

    try:
        if CONFIG_PATH.exists():
            config.read(str(CONFIG_PATH), encoding="utf-8")
            if config.has_section("viewer"):
                for key in DEFAULTS:
                    if config.has_option("viewer", key):
                        result[key] = config.get("viewer", key)
    except Exception as e:
        print(f"读取配置文件失败: {e}")

    return result


def save_config(settings: dict):
    """将用户配置保存到 INI 文件。

    Args:
        settings: 要保存的配置字典，键为配置项名称，值为字符串。
    """
    config = configparser.ConfigParser()
    config["viewer"] = settings

    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            config.write(f)
    except Exception as e:
        print(f"保存配置文件失败: {e}")
