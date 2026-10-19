"""Gate-by-gate decision trace. Shown to the user ('How I decided'); never persisted, never raw content."""
from __future__ import annotations

from core.domain.schemas import TraceStep


class Trace:
    def __init__(self) -> None:
        self.steps: list[TraceStep] = []

    def add(self, stage: str, status: str, detail: str) -> None:
        """status: pass | flag | skip | block"""
        self.steps.append(TraceStep(stage=stage, status=status, detail=detail[:240]))
