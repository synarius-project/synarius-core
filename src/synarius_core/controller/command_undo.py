from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias

UndoRedoPair: TypeAlias = tuple[list[str], list[str]]


class CommandUndoManager:
    """Maintains undo/redo stacks of command-line transactions (each entry is protocol lines)."""

    __slots__ = ("max_undo_depth", "_recording", "_undo_stack", "_redo_stack")

    def __init__(self, max_depth: int = 100, *, recording: bool = True) -> None:
        self.max_undo_depth = max(1, int(max_depth))
        self._recording = bool(recording)
        self._undo_stack: list[UndoRedoPair] = []
        self._redo_stack: list[UndoRedoPair] = []

    @property
    def undo_stack(self) -> list[UndoRedoPair]:
        return self._undo_stack

    @property
    def redo_stack(self) -> list[UndoRedoPair]:
        return self._redo_stack

    @property
    def recording_enabled(self) -> bool:
        return self._recording

    @recording_enabled.setter
    def recording_enabled(self, value: bool) -> None:
        self._recording = bool(value)

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()

    def record_pair(self, pair: UndoRedoPair | None) -> None:
        if pair is None or not self._recording:
            return
        self._append_undo(pair[0], pair[1])
        self._redo_stack.clear()

    def _append_undo(self, undo_cmds: list[str], redo_cmds: list[str]) -> None:
        self._undo_stack.append((undo_cmds, redo_cmds))
        while len(self._undo_stack) > self.max_undo_depth:
            self._undo_stack.pop(0)

    def prepare_undo(self) -> UndoRedoPair | None:
        if not self._undo_stack:
            return None
        return self._undo_stack.pop()

    def complete_undo(self, pair: UndoRedoPair) -> None:
        self._redo_stack.append(pair)

    def prepare_redo(self) -> UndoRedoPair | None:
        if not self._redo_stack:
            return None
        return self._redo_stack.pop()

    def complete_redo(self, undo_cmds: list[str], redo_cmds: list[str]) -> None:
        self._append_undo(undo_cmds, redo_cmds)

    def run_without_recording(self, fn: Callable[[], None]) -> None:
        prev = self._recording
        self._recording = False
        try:
            fn()
        finally:
            self._recording = prev
