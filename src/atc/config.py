import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_env_file(path):
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str
    model: str
    effort: str
    data_dir: Path
    notes_dir: Path
    xplane_dir: Path
    xplane_host: str
    xplane_port: int
    xplane_listen_port: int
    region: str
    max_tool_steps: int
    stt_model: str
    ptt_button: int


def _path(name, default):
    return Path(os.environ.get(name, default)).expanduser()


@lru_cache(maxsize=1)
def get_settings():
    _load_env_file(ROOT / ".env")
    return Settings(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        model=os.environ.get("ATC_MODEL", "claude-sonnet-5-5"),
        effort=os.environ.get("ATC_EFFORT", "low"),
        data_dir=_path("ATC_DATA_DIR", ROOT / "data"),
        notes_dir=_path("ATC_NOTES_DIR", ROOT / "notes"),
        xplane_dir=_path("ATC_XPLANE_DIR", "~/X-Plane 12"),
        xplane_host=os.environ.get("ATC_XPLANE_HOST", "127.0.0.1"),
        xplane_port=int(os.environ.get("ATC_XPLANE_PORT", "49000")),
        xplane_listen_port=int(os.environ.get("ATC_XPLANE_LISTEN_PORT", "49001")),
        region=os.environ.get("ATC_REGION", "FAA").upper(),
        max_tool_steps=int(os.environ.get("ATC_MAX_TOOL_STEPS", "6")),
        stt_model=os.environ.get("ATC_STT_MODEL", "base.en"),
        ptt_button=int(os.environ.get("ATC_PTT_BUTTON", "-1")),
    )
