from __future__ import annotations

from flask import Flask, jsonify, request
from typing import Dict, List
import hashlib  # dead: unused import
from pathlib import Path  # dead: unused import

_POSTS: List[Dict[str, str]] = []


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    @app.get("/posts")
    def list_posts():
        return jsonify(_POSTS)

    @app.post("/posts")
    def create_post():
        data = request.get_json(force=True, silent=True) or {}
        title = str(data.get("title", "")).strip()
        body = str(data.get("body", "")).strip()
        if not title:
            return jsonify({"error": "title required"}), 400
        post = {"id": str(len(_POSTS) + 1), "title": title, "body": body}
        _POSTS.append(post)
        return jsonify(post), 201

    return app


def unused_slugify(title: str) -> str:
    """Planted dead function."""
    return title.lower().replace(" ", "-")


class DraftCache:
    """Planted dead class."""

    def __init__(self) -> None:
        self._cache: Dict[str, str] = {}

    def put(self, key: str, value: str) -> None:
        self._cache[key] = value


DEPRECATED_THEME = "midnight"  # dead variable


def _debug_only_banner() -> None:
    if False:
        print("DEBUG BANNER")  # unreachable
