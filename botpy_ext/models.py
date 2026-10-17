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
