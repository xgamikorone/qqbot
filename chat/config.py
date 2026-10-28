from dataclasses import dataclass
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent

@dataclass(frozen=True)
class ChatConfig:
    enabled: bool = False
    allowed_channel_ids: tuple[str, ...] = ()
    max_input_chars: int = 2000
    max_context_chars: int = 8000
    max_output_tokens: int = 800
    max_concurrent_requests: int = 3
    max_pending_requests: int = 20
    request_timeout_seconds: int = 45
    daily_requests_per_user: int = 30
    retention_days: int = 7
    prompt: str = "你是 QQ 频道中的 AI 助手，请简洁友善地回答。"

def load_config(path=None):
    data = yaml.safe_load(Path(path or ROOT / "config/chat.yaml").read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or set(data) - (set(ChatConfig.__dataclass_fields__) - {"prompt"}):
        raise ValueError("Invalid chat configuration")
    if type(data.get("enabled", False)) is not bool:
        raise ValueError("enabled must be boolean")
    channels = data.get("allowed_channel_ids", [])
    if not isinstance(channels, list) or any(not isinstance(x, str) or not x.isdigit() for x in channels):
        raise ValueError("Channel IDs must be quoted numeric strings")
    data["allowed_channel_ids"] = tuple(channels)
    for key, value in data.items():
        if key not in {"enabled", "allowed_channel_ids"} and (type(value) is not int or value <= 0):
            raise ValueError("Chat limits must be positive integers")
    config = ChatConfig(**data, prompt=(ROOT / "config/chat_prompt.txt").read_text(encoding="utf-8").strip())
    if not config.prompt or len(config.prompt) + config.max_input_chars > config.max_context_chars:
        raise ValueError("Chat context budget is too small")
    return config
