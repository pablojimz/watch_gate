"""Formatters de salida para la CLI de WatchGate (Strategy Pattern)."""

from __future__ import annotations

from watchgate.formatters.console import render_console
from watchgate.formatters.github import render_github_annotations
from watchgate.formatters.sarif import render_sarif

__all__ = ["render_console", "render_github_annotations", "render_sarif"]
