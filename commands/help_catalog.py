from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
from typing import Mapping


@dataclass(frozen=True)
class CommandHelp:
    """一个命令对外展示的帮助信息。"""

    title: str
    category: str
    summary: str
    usage: str | None = None
    examples: tuple[str, ...] = ()
    details: str | None = None
    lookup_names: tuple[str, ...] = ()
    show_in_overview: bool = True


class HelpCatalog:
    """根据命令注册表查找并渲染帮助信息。"""

    def __init__(self, registry: Mapping[str, type]):
        self._registry = registry

    def render(self, query: str | None = None, *, include_owner: bool = False) -> str:
        entries = self._entries(include_owner=include_owner)
        if query is None or not query.strip():
            return self._render_overview(entries)

        normalized_query = query.strip().lstrip("/").casefold()
        command = self._lookup(entries).get(normalized_query)
        if command is not None:
            return self._render_command(command)

        categories = {
            command.help.category.casefold(): command.help.category
            for command in entries
            if command.help is not None
        }
        category = categories.get(normalized_query)
        if category is not None:
            category_entries = [
                command
                for command in entries
                if command.help is not None and command.help.category == category
            ]
            return self._render_category(category, category_entries)

        suggestions = self._suggest(normalized_query, entries)
        message = f"没有找到“{query.strip()}”的帮助信息。"
        if suggestions:
            message += "\n\n你可能想找：\n" + "\n".join(
                f"- /帮助 {title}" for title in suggestions
            )
        return message + "\n\n输入 /帮助 查看全部分类。"

    def _entries(self, *, include_owner: bool) -> list[type]:
        entries: list[type] = []
        seen: set[type] = set()
        for command in self._registry.values():
            if command in seen:
                continue
            seen.add(command)
            if getattr(command, "hidden", False):
                continue
            if getattr(command, "owner_only", False) and not include_owner:
                continue
            if getattr(command, "help", None) is None:
                continue
            entries.append(command)
        return entries

    def _lookup(self, entries: list[type]) -> dict[str, type]:
        lookup: dict[str, type] = {}
        visible = set(entries)
        for alias, command in self._registry.items():
            if command in visible:
                lookup.setdefault(alias.casefold(), command)

        for command in entries:
            help_info = command.help
            names = (
                command.name,
                command.cn_name,
                help_info.title,
                *help_info.lookup_names,
            )
            for name in names:
                lookup.setdefault(name.casefold(), command)
        return lookup

    def _render_overview(self, entries: list[type]) -> str:
        categories: dict[str, list[type]] = {}
        for command in entries:
            if command.help.show_in_overview:
                categories.setdefault(command.help.category, []).append(command)

        lines = [
            "丸子bot 帮助",
            "输入 /帮助 <功能名或命令名> 查看详细用法。",
        ]
        for category, commands in categories.items():
            lines.append(f"\n【{category}】")
            lines.extend(
                f"/{command.help.title} — {command.help.summary}"
                for command in commands
            )
        return "\n".join(lines)

    def _render_category(self, category: str, entries: list[type]) -> str:
        lines = [f"【{category}】"]
        lines.extend(
            f"/{command.help.title} — {command.help.summary}" for command in entries
        )
        lines.append("\n输入 /帮助 <功能名> 查看详细用法。")
        return "\n".join(lines)

    def _render_command(self, command: type) -> str:
        help_info = command.help
        if help_info.details:
            return help_info.details.strip()

        lines = [help_info.title, help_info.summary]
        if help_info.usage:
            lines.extend(("", "用法：", help_info.usage))
        if help_info.examples:
            lines.extend(("", "示例：", *help_info.examples))

        aliases = [
            alias
            for alias, registered_command in self._registry.items()
            if registered_command is command and alias != help_info.title
        ]
        if aliases:
            lines.extend(("", "别名：", "、".join(f"/{alias}" for alias in aliases)))
        return "\n".join(lines)

    def _suggest(self, query: str, entries: list[type]) -> list[str]:
        lookup = self._lookup(entries)
        matches = get_close_matches(query, list(lookup), n=3, cutoff=0.45)
        suggestions: list[str] = []
        for match in matches:
            title = lookup[match].help.title
            if title not in suggestions:
                suggestions.append(title)
        return suggestions
