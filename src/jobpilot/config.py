"""运行时目录、profile / searches / .env 加载。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parent.parent

_ENV_KEYS = ("OPENAI_BASE_URL", "OPENAI_API_KEY", "JOBPILOT_MODEL")


def runtime_dir() -> Path:
    d = Path(os.environ.get("JOBPILOT_HOME", str(Path.home() / ".jobpilot-cn")))
    d.mkdir(parents=True, exist_ok=True)
    (d / "cookies").mkdir(exist_ok=True)
    (d / "reports").mkdir(exist_ok=True)
    return d


def db_path() -> Path:
    return runtime_dir() / "db.sqlite3"


def cookies_dir() -> Path:
    return runtime_dir() / "cookies"


def reports_dir() -> Path:
    return runtime_dir() / "reports"


def profile_path() -> Path:
    return runtime_dir() / "profile.json"


def resume_path() -> Path:
    return runtime_dir() / "resume.txt"


def searches_path() -> Path:
    return runtime_dir() / "searches.yaml"


def load_env() -> None:
    """从 runtime 目录或仓库根的 .env 读取配置（不覆盖已有环境变量）。"""
    for candidate in (runtime_dir() / ".env", REPO_ROOT / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key in _ENV_KEYS and key not in os.environ:
                os.environ[key] = value


def load_profile() -> dict:
    p = profile_path()
    if not p.exists():
        raise FileNotFoundError(
            f"未找到 {p}。先运行: uv run python scripts/build_profile.py --resume <简历路径>"
        )
    return json.loads(p.read_text(encoding="utf-8"))


def load_resume() -> str:
    p = resume_path()
    if not p.exists():
        raise FileNotFoundError(
            f"未找到 {p}。先运行: uv run python scripts/build_profile.py --resume <简历路径>"
        )
    return p.read_text(encoding="utf-8")


def load_searches() -> dict:
    p = searches_path()
    if not p.exists():
        example = REPO_ROOT / "searches.example.yaml"
        if example.exists():
            import shutil

            shutil.copy(example, p)
        else:
            raise FileNotFoundError(f"未找到 {p}，请手动创建（格式见 searches.example.yaml）")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    return {k: v for k, v in (data or {}).items() if k in ("boss", "liepin")}


def llm_settings() -> tuple[str, str, str]:
    """返回 (base_url, api_key, model)，缺项时抛出带指引的错误。"""
    load_env()
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("JOBPILOT_MODEL", "")
    missing = []
    if not api_key:
        missing.append("OPENAI_API_KEY")
    if not model:
        missing.append("JOBPILOT_MODEL")
    if missing:
        raise RuntimeError(
            f"缺少环境变量: {', '.join(missing)}。"
            f"请在 {runtime_dir() / '.env'} 或仓库根 .env 中配置（参考 .env.example）"
        )
    return base_url, api_key, model
