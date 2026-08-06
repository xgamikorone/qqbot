from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import yaml


DEFAULT_UPDATES_PATH = Path(__file__).resolve().parent / "config" / "user_updates.yaml"
ALLOWED_AUDIENCES = {"user", "internal"}


class UserUpdatesConfigError(ValueError):
    """更新记录文件无法解析或验证。"""


@dataclass(frozen=True)
class UserUpdate:
    published_at: date
    title: str
    audience: str
    changes: tuple[str, ...]

    def render(self) -> str:
        lines = [
            f"最近更新 · {self.published_at.isoformat()}",
            self.title,
            "",
        ]
        lines.extend(f"- {change}" for change in self.changes)
        return "\n".join(lines)


def load_latest_user_update(
    path: str | Path = DEFAULT_UPDATES_PATH,
) -> UserUpdate | None:
    updates = load_updates(path)
    user_updates = [update for update in updates if update.audience == "user"]
    return max(user_updates, key=lambda update: update.published_at, default=None)


def load_updates(path: str | Path = DEFAULT_UPDATES_PATH) -> tuple[UserUpdate, ...]:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            raw_config = yaml.safe_load(file)
    except OSError as error:
        raise UserUpdatesConfigError(
            f"cannot read user updates config {config_path}: {error}"
        ) from error
    except yaml.YAMLError as error:
        raise UserUpdatesConfigError(
            f"invalid YAML in user updates config {config_path}: {error}"
        ) from error

    root = _require_mapping(raw_config, "config root")
    _reject_unknown_keys(root, {"updates"}, "config root")
    raw_updates = root.get("updates", [])
    if not isinstance(raw_updates, list):
        raise UserUpdatesConfigError("updates must be a list")

    return tuple(
        _parse_update(raw_update, index)
        for index, raw_update in enumerate(raw_updates)
    )


def _parse_update(raw_update: Any, index: int) -> UserUpdate:
    location = f"updates[{index}]"
    update = _require_mapping(raw_update, location)
    _reject_unknown_keys(
        update,
        {"published_at", "title", "audience", "changes"},
        location,
    )

    published_at_value = _require_string(
        update.get("published_at"), f"{location}.published_at"
    )
    try:
        published_at = date.fromisoformat(published_at_value)
    except ValueError as error:
        raise UserUpdatesConfigError(
            f"{location}.published_at must use YYYY-MM-DD format"
        ) from error

    title = _require_string(update.get("title"), f"{location}.title")
    audience = _require_string(update.get("audience"), f"{location}.audience")
    if audience not in ALLOWED_AUDIENCES:
        allowed = ", ".join(sorted(ALLOWED_AUDIENCES))
        raise UserUpdatesConfigError(
            f"{location}.audience must be one of: {allowed}"
        )

    raw_changes = update.get("changes")
    if not isinstance(raw_changes, list) or not raw_changes:
        raise UserUpdatesConfigError(f"{location}.changes must be a non-empty list")
    changes = tuple(
        _require_string(change, f"{location}.changes[{change_index}]")
        for change_index, change in enumerate(raw_changes)
    )

    return UserUpdate(
        published_at=published_at,
        title=title,
        audience=audience,
        changes=changes,
    )


def _require_mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise UserUpdatesConfigError(f"{location} must be a mapping")
    return value


def _require_string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UserUpdatesConfigError(f"{location} must be a non-empty string")
    return value.strip()


def _reject_unknown_keys(
    mapping: Mapping[str, Any], allowed: set[str], location: str
) -> None:
    unknown = set(mapping) - allowed
    if unknown:
        names = ", ".join(sorted(str(key) for key in unknown))
        raise UserUpdatesConfigError(f"unknown keys in {location}: {names}")
