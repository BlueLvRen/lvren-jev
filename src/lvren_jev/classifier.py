from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .definitions import DecisionDefinition
from .results import ClassificationResult
from .runtime import DecisionRequest, JevResponse, JevRuntime


class SemanticClassifier:
    """Turn text into a typed category using a definition and shared runtime."""

    def __init__(self, definition: DecisionDefinition, runtime: JevRuntime | Any):
        if not isinstance(definition, DecisionDefinition):
            raise TypeError("definition must be a DecisionDefinition")
        if not hasattr(runtime, "execute"):
            raise TypeError("runtime must provide execute(request)")
        self.definition = definition
        self.runtime = runtime

    @classmethod
    def from_definition(
        cls,
        definition: DecisionDefinition,
        *,
        runtime: JevRuntime | Any,
    ) -> "SemanticClassifier":
        return cls(definition, runtime)

    def classify(self, text: str) -> ClassificationResult:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("classification text must be a non-empty string")
        request = DecisionRequest(
            state={self.definition.input_field: text},
            questions={
                self.definition.name: {
                    "type": "choice",
                    "instructions": self._instructions(),
                    "criteria": {
                        value: category.description
                        for value, category in self.definition.categories.items()
                    },
                }
            },
        )
        raw_response = self.runtime.execute(request)
        answer = self._extract_answer(raw_response)
        selected = answer.get("choice", answer.get("selected", answer.get("value")))
        if not isinstance(selected, str) or not selected:
            raise ValueError("Jev response does not contain a selected category")
        category = self.definition.categories.get(selected)
        if category is None:
            raise ValueError(f"unknown category returned by Jev: {selected}")

        probabilities = answer.get("probabilities")
        if probabilities is not None and not isinstance(probabilities, Mapping):
            raise ValueError("Jev response probabilities must be an object")
        confidence = answer.get("confidence")
        if confidence is None and probabilities:
            confidence = max(float(value) for value in probabilities.values())
        if confidence is None:
            confidence = 0.0
        confidence = float(confidence)
        if not 0 <= confidence <= 1:
            raise ValueError("Jev response confidence must be between 0 and 1")

        if confidence < self.definition.policy.threshold:
            fallback = self.definition.policy.fallback
            return ClassificationResult(
                value=fallback.value,
                label=fallback.label,
                confidence=confidence,
                probabilities=probabilities,
                fallback=True,
            )
        return ClassificationResult(
            value=category.value,
            label=category.label,
            confidence=confidence,
            probabilities=probabilities,
            fallback=False,
        )

    def _instructions(self) -> str:
        if self.definition.instructions:
            return self.definition.instructions
        return "Choose the category that best matches the input."

    def _extract_answer(self, response: JevResponse | Mapping[str, Any]) -> Mapping[str, Any]:
        answers = response.answers if isinstance(response, JevResponse) else response.get("answers")
        if not isinstance(answers, Mapping) or not answers:
            raise ValueError("Jev response does not contain answers")
        answer = answers.get(self.definition.name)
        if answer is None and len(answers) == 1:
            answer = next(iter(answers.values()))
        if hasattr(answer, "model_dump"):
            answer = answer.model_dump()
        if isinstance(answer, str):
            return {"choice": answer}
        if not isinstance(answer, Mapping):
            raise ValueError("Jev classification answer must be an object")
        return answer
