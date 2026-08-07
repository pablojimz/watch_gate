"""Adaptador de Hooks servidor para Git (watchgate/adapters/git_hook/)."""

from __future__ import annotations

from watchgate.adapters.git_hook.pre_receive import run_pre_receive

__all__ = ["run_pre_receive"]
