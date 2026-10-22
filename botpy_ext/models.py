"""Response types for the QQ global custom menu API."""

from typing import Literal, NotRequired, TypedDict


class MenuSwitch(TypedDict):
    switch_id: str
    default: bool


class SubMenuItem(TypedDict):
    name: str
    type: Literal["send_message", "link"]
    send_message: NotRequired[str]
    link: NotRequired[str]


class MenuItem(TypedDict):
    name: str
    type: Literal["switch", "send_message", "link", "menu"]
    sub_menu_items: NotRequired[list[SubMenuItem]]
    send_message: NotRequired[str]
    link: NotRequired[str]
    switch: NotRequired[MenuSwitch]


class Menu(TypedDict):
    items: list[MenuItem]


class GlobalMenuResponse(TypedDict):
    version: int
    menu: Menu | None


PanelScope = Literal["c2c", "group", "channel", "dm"]
TargetType = Literal["all", "specific"]


class VersionResponse(TypedDict):
    version: int


class PanelItem(TypedDict):
    name: str
    type: Literal["command", "link"]
    desc: NotRequired[str]
    only_admin: NotRequired[bool]
    link: NotRequired[str]


class Panel(TypedDict, total=False):
    items: list[PanelItem]
    remark: str
    version: int


class PanelCreatedResponse(TypedDict):
    panel_id: str


class PanelRecord(TypedDict):
    panel_id: str
    scope: PanelScope
    target_type: TargetType
    panel: Panel
    created_at: str
    updated_at: str
    version: int
    user_openids: NotRequired[list[str]]
    group_openids: NotRequired[list[str]]


class PanelListResponse(TypedDict):
    records: list[PanelRecord]
    next_cursor: str
    is_end: bool


class URLLinkData(TypedDict):
    url: str


class GenerateURLLinkResponse(TypedDict):
    data: URLLinkData
