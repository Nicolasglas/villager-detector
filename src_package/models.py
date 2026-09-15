"""Immutable data models shared by detector services."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """The normalized template score and resulting availability state."""

    score: float
    available: bool
