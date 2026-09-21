from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ReleaseLevel(StrEnum):
    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"


@dataclass(frozen=True)
class CommitEvidence:
    sha: str
    subject: str
    body: str
    diff: str

    def prompt(self) -> str:
        return (
            f"Commit: {self.sha}\n"
            f"Commit subject and body:\n{self.body}\n\n"
            f"Actual commit diff:\n{self.diff}"
        )


@dataclass(frozen=True)
class ReleaseEvidence:
    ready: bool
    code: str | None = None
    message: str | None = None
    target_commit: str | None = None
    baseline_tag: str | None = None
    baseline_commit: str | None = None
    commits: tuple[CommitEvidence, ...] = ()
    diff: str = ""
    diff_sha256: str | None = None

    @classmethod
    def rejected(
        cls,
        code: str,
        message: str,
        *,
        target_commit: str | None = None,
    ) -> "ReleaseEvidence":
        return cls(
            ready=False,
            code=code,
            message=message,
            target_commit=target_commit,
        )

    @property
    def diff_bytes(self) -> int:
        return len(self.diff.encode("utf-8"))

    def prompt(self) -> str:
        if not self.ready:
            raise ValueError("release evidence is not ready")
        commit_text = "\n\n".join(commit.prompt() for commit in self.commits)
        return (
            f"Target commit: {self.target_commit}\n"
            f"Previous release tag: {self.baseline_tag} ({self.baseline_commit})\n"
            f"All commit bodies and their actual diffs:\n{commit_text}\n\n"
            f"Cumulative actual diff ({self.diff_bytes} UTF-8 bytes, "
            f"sha256={self.diff_sha256}):\n{self.diff}"
        )


@dataclass(frozen=True)
class DecisionObservation:
    value: str
    confidence: float
    fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "confidence": self.confidence,
            "fallback": self.fallback,
        }


@dataclass(frozen=True)
class ReleaseResult:
    status: str
    code: str
    message: str
    version: str | None = None
    level: ReleaseLevel | None = None
    target_commit: str | None = None
    baseline_tag: str | None = None
    links: dict[str, str] = field(default_factory=dict)
    completed_actions: tuple[str, ...] = ()
    failed_step: str | None = None
    remote_state: dict[str, Any] = field(default_factory=dict)
    observations: tuple[DecisionObservation, ...] = ()

    @classmethod
    def rejected(cls, code: str, message: str, **kwargs: Any) -> "ReleaseResult":
        return cls(status="rejected", code=code, message=message, **kwargs)

    @classmethod
    def failed(cls, code: str, message: str, **kwargs: Any) -> "ReleaseResult":
        return cls(status="failed", code=code, message=message, **kwargs)

    @classmethod
    def ready_result(
        cls,
        *,
        version: str | None = None,
        level: ReleaseLevel,
        message: str,
        **kwargs: Any,
    ) -> "ReleaseResult":
        return cls(
            status="ready",
            code="READY",
            message=message,
            version=version,
            level=level,
            **kwargs,
        )

    @classmethod
    def succeeded(cls, version: str, message: str, **kwargs: Any) -> "ReleaseResult":
        return cls(
            status="succeeded",
            code="PUBLISHED",
            message=message,
            version=version,
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "code": self.code,
            "message": self.message,
            "version": self.version,
            "level": self.level.value if self.level is not None else None,
            "target_commit": self.target_commit,
            "baseline_tag": self.baseline_tag,
            "links": dict(self.links),
            "completed_actions": list(self.completed_actions),
            "failed_step": self.failed_step,
            "remote_state": dict(self.remote_state),
            "observations": [item.to_dict() for item in self.observations],
        }


def make_diff_digest(diff: str) -> str:
    return hashlib.sha256(diff.encode("utf-8")).hexdigest()
