from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClassificationResult:
    value: str
    label: str
    confidence: float
    probabilities: Mapping[str, float] | None = None
    fallback: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:
            raise ValueError("result value must be a non-empty string")
        if not isinstance(self.label, str) or not self.label:
            raise ValueError("result label must be a non-empty string")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise ValueError("result confidence must be a number")
        if not 0 <= self.confidence <= 1:
            raise ValueError("result confidence must be between 0 and 1")
        if self.probabilities is not None:
            if not isinstance(self.probabilities, Mapping):
                raise ValueError("result probabilities must be an object")
            normalized = {str(key): float(value) for key, value in self.probabilities.items()}
            if any(value < 0 or value > 1 for value in normalized.values()):
                raise ValueError("result probabilities must be between 0 and 1")
            object.__setattr__(self, "probabilities", normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "label": self.label,
            "confidence": self.confidence,
            "probabilities": dict(self.probabilities or {}),
            "fallback": self.fallback,
        }


@dataclass(frozen=True)
class ScoreResult:
    score: float
    confidence: float
    legend: Mapping[str, Any] | None = None
    probabilities: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise ValueError("result score must be a number")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise ValueError("result confidence must be a number")
        if not 0 <= self.confidence <= 1:
            raise ValueError("result confidence must be between 0 and 1")
        if self.legend is not None and not isinstance(self.legend, Mapping):
            raise ValueError("result legend must be an object")
        if self.probabilities is not None:
            if not isinstance(self.probabilities, Mapping):
                raise ValueError("result probabilities must be an object")
            normalized = {str(key): float(value) for key, value in self.probabilities.items()}
            if any(value < 0 or value > 1 for value in normalized.values()):
                raise ValueError("result probabilities must be between 0 and 1")
            object.__setattr__(self, "probabilities", normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": float(self.score),
            "confidence": float(self.confidence),
            "legend": dict(self.legend or {}),
            "probabilities": dict(self.probabilities or {}),
        }


@dataclass(frozen=True)
class NoulResult:
    probability: float

    def __post_init__(self) -> None:
        if isinstance(self.probability, bool) or not isinstance(self.probability, (int, float)):
            raise ValueError("result probability must be a number")
        if not 0 <= self.probability <= 1:
            raise ValueError("result probability must be between 0 and 1")

    def is_true(self, *, threshold: float = 0.5) -> bool:
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ValueError("threshold must be a number")
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        return self.probability >= threshold

    def to_dict(self) -> dict[str, Any]:
        return {"probability": float(self.probability)}
