import dataclasses
import pathlib
import re
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Group openids are opaque platform identifiers, not numeric channel IDs.
_GROUP_OPENID = re.compile(r"[A-Za-z0-9_-]{1,64}")


@dataclasses.dataclass(frozen=True)
class ChatConfig:
    enabled: bool = False
    allowed_channel_ids: tuple[str, ...] = ()
    allowed_group_ids: tuple[str, ...] = ()
    max_input_chars: int = 2000
    max_context_chars: int = 8000
    max_output_tokens: int = 800
    max_concurrent_requests: int = 3
    max_pending_requests: int = 20
    request_timeout_seconds: int = 45
    daily_requests_per_user: int = 30
    retention_days: int = 7
    web_enabled: bool = False
    summary_construct_ids: bool = False
    web_max_searches: int = 2
    web_max_fetches: int = 2
    web_max_context_chars: int = 8000
    web_timeout_seconds: int = 90
    prompt: str = "你是 QQ 频道中的 AI 助手，请简洁友善地回答。"


def load_config(path: str | pathlib.Path | None = None) -> ChatConfig:
    """Loads validated chat limits and the existing persona prompt."""
    data = yaml.safe_load(
        pathlib.Path(path or ROOT / "config/chat.yaml").read_text(
            encoding="utf-8")) or {}
    if not isinstance(data, dict) or set(data) - (
            set(ChatConfig.__dataclass_fields__) - {"prompt"}):
        raise ValueError("Invalid chat configuration")
    for switch in ("enabled", "web_enabled", "summary_construct_ids"):
        if type(data.get(switch, False)) is not bool:
            raise ValueError("Chat switches must be boolean")
    channels = data.get("allowed_channel_ids", [])
    if not isinstance(channels, list) or any(
        not isinstance(x, str) or not x.isdigit() for x in channels
    ):
        raise ValueError("Channel IDs must be quoted numeric strings")
    data["allowed_channel_ids"] = tuple(channels)
    groups = data.get("allowed_group_ids", [])
    if not isinstance(groups, list) or any(
        not isinstance(x, str) or not _GROUP_OPENID.fullmatch(x) for x in groups
    ):
        raise ValueError("Group IDs must be nonempty openid strings")
    if len(set(groups)) != len(groups):
        raise ValueError("Group IDs must be distinct")
    data["allowed_group_ids"] = tuple(groups)
    for key, value in data.items():
        if key not in {
            "enabled",
            "web_enabled",
            "summary_construct_ids",
            "allowed_channel_ids",
            "allowed_group_ids",
        } and (type(value) is not int or value <= 0):
            raise ValueError("Chat limits must be positive integers")
    config = ChatConfig(**data,
                        prompt=(ROOT / "config/chat_prompt.txt").read_text(
                            encoding="utf-8").strip())
    if not config.prompt or len(
            config.prompt) + config.max_input_chars > config.max_context_chars:
        raise ValueError("Chat context budget is too small")
    if (config.web_max_searches > 2 or config.web_max_fetches > 2 or
            config.web_max_context_chars > 20000 or
            config.web_timeout_seconds > 180):
        raise ValueError("Chat web limits exceed safety caps")
    return config
