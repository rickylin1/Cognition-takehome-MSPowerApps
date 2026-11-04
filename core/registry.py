"""Tools shown on the home page. Each app registers its name, URL, and required permission."""

from dataclasses import dataclass

from core.auth import User
from core.permissions import has_permission


@dataclass(frozen=True)
class Tool:
    name: str
    url: str
    permission: str


_tools: list[Tool] = []


def register_tool(name: str, url: str, permission: str) -> None:
    _tools.append(Tool(name, url, permission))


def visible_tools(user: User) -> list[Tool]:
    return [t for t in _tools if has_permission(user, t.permission)]
