from __future__ import annotations

from pathlib import Path
from typing import Any

from ..decision import SemanticClassifier
from ..loader import load_decision_definition
from .models import (
    DecisionObservation,
    ReleaseEvidence,
    ReleaseLevel,
    ReleaseResult,
)
from .versioning import max_level


_DEFINITIONS = Path(__file__).with_name("definitions")


class ReleaseDecisionEngine:
    """Run the two release decisions while keeping business logic in this package."""

    def __init__(
        self,
        *,
        runtime: Any,
        suitability_definition: str | Path | None = None,
        level_definition: str | Path | None = None,
    ) -> None:
        self.runtime = runtime
        self.suitability = load_decision_definition(
            suitability_definition or _DEFINITIONS / "release_suitability.yaml"
        )
        self.level = load_decision_definition(
            level_definition or _DEFINITIONS / "release_level.yaml"
        )

    def assess(self, evidence: ReleaseEvidence) -> ReleaseResult:
        if not evidence.ready:
            return ReleaseResult.rejected(
                evidence.code or "INVALID_EVIDENCE",
                evidence.message or "发布证据不可用",
                target_commit=evidence.target_commit,
                baseline_tag=evidence.baseline_tag,
            )

        observations: list[DecisionObservation] = []
        try:
            suitability = SemanticClassifier.from_definition(
                self.suitability, runtime=self.runtime
            ).classify(evidence.prompt())
        except (TypeError, ValueError):
            return self._uncertain(evidence, observations)
        suitability_observation = DecisionObservation(
            value=suitability.value,
            confidence=suitability.confidence,
            fallback=suitability.fallback,
        )
        observations.append(suitability_observation)
        if suitability.fallback or suitability.value == "pending_review":
            return self._uncertain(evidence, observations)
        if suitability.value != "publish":
            return ReleaseResult.rejected(
                "SEMANTIC_REJECTED",
                "Jev 判断累计变更不适合打包发布",
                target_commit=evidence.target_commit,
                baseline_tag=evidence.baseline_tag,
                observations=tuple(observations),
            )

        levels: list[ReleaseLevel] = []
        classifier = SemanticClassifier.from_definition(self.level, runtime=self.runtime)
        for commit in evidence.commits:
            try:
                result = classifier.classify(commit.prompt())
            except (TypeError, ValueError):
                return self._uncertain(evidence, observations)
            observation = DecisionObservation(
                value=result.value,
                confidence=result.confidence,
                fallback=result.fallback,
            )
            observations.append(observation)
            if result.fallback or result.value == "pending_review":
                return self._uncertain(evidence, observations)
            try:
                levels.append(ReleaseLevel(result.value))
            except ValueError:
                return self._uncertain(evidence, observations)

        if not levels:
            return ReleaseResult.rejected(
                "NO_CHANGE_DECISION",
                "没有可供版本级别判断的提交证据",
                target_commit=evidence.target_commit,
                baseline_tag=evidence.baseline_tag,
                observations=tuple(observations),
            )
        level = max_level(levels)
        return ReleaseResult.ready_result(
            level=level,
            message=f"累计变更适合发布，最高影响级别为 {level.value.upper()}",
            target_commit=evidence.target_commit,
            baseline_tag=evidence.baseline_tag,
            observations=tuple(observations),
        )

    @staticmethod
    def _uncertain(
        evidence: ReleaseEvidence,
        observations: list[DecisionObservation],
    ) -> ReleaseResult:
        return ReleaseResult.rejected(
            "SEMANTIC_UNCERTAIN",
            "Jev 判断置信度不足或结果模糊，需要人工复核；未执行发布副作用",
            target_commit=evidence.target_commit,
            baseline_tag=evidence.baseline_tag,
            observations=tuple(observations),
        )
