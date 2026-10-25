from __future__ import annotations

from dataclasses import dataclass, field
from typing import List
import json  # dead: unused import
from collections import OrderedDict  # dead: unused import


@dataclass
class TodoItem:
    title: str
    done: bool = False


@dataclass
class TodoList:
    items: List[TodoItem] = field(default_factory=list)

    def add(self, title: str) -> TodoItem:
        item = TodoItem(title=title)
        self.items.append(item)
        return item

    def complete(self, index: int) -> None:
        self.items[index].done = True

    def pending(self) -> List[TodoItem]:
        return [i for i in self.items if not i.done]

    def count(self) -> int:
        return len(self.items)


def unused_helper_format_titles(items: List[TodoItem]) -> str:
    """Planted dead function — never called."""
    return ", ".join(i.title for i in items)


class AbandonedExporter:
    """Planted dead class — never instantiated."""

    def __init__(self, path: str) -> None:
        self.path = path

    def dump(self, items: List[TodoItem]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("\n".join(i.title for i in items))


LEGACY_MAX_ITEMS = 10_000  # dead variable


def maybe_legacy_path(flag: bool) -> None:
    if False:  # unreachable
        print("legacy path")
        return
    return None
