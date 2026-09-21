from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .definitions import DecisionDefinition
from .results import ClassificationResult, NoulResult, ScoreResult
from .runtime import DecisionRequest, JevResponse


class _PrimitiveEvaluator:
    def __init__(
        self,
        *,
        name: str,
        runtime: Any,
        instructions: str | None = None,
        input_field: str | None = None,
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("decision name must be a non-empty string")
        if not hasattr(runtime, "execute"):
            raise TypeError("runtime must provide execute(request)")
        if instructions is not None and not isinstance(instructions, str):
            raise TypeError("instructions must be a string or None")
        if input_field is not None and (not isinstance(input_field, str) or not input_field.strip()):
            raise ValueError("input_field must be a non-empty string or None")
        self.name = name
        self.runtime = runtime
        self.instructions = instructions
        self.input_field = input_field

    def _prepare_state(self, value: Any) -> Any:
        if self.input_field is None:
            return value
        if not isinstance(value, str) or not value.strip():
            raise ValueError("decision input must be a non-empty string")
        return {self.input_field: value}

    def _execute(self, state: Any, question: Mapping[str, Any]) -> Mapping[str, Any]:
        response = self.runtime.execute(
            DecisionRequest(
                state=state,
                questions={self.name: dict(question)},
            )
        )
        return self._extract_answer(response)

    def _extract_answer(self, response: JevResponse | Mapping[str, Any]) -> Mapping[str, Any]:
        answers = response.answers if isinstance(response, JevResponse) else response.get("answers")
        if not isinstance(answers, Mapping) or not answers:
            raise ValueError("Jev response does not contain answers")
        answer = answers.get(self.name)
        if answer is None and len(answers) == 1:
            answer = next(iter(answers.values()))
        if hasattr(answer, "model_dump"):
            answer = answer.model_dump()
        if isinstance(answer, str):
            return {"choice": answer}
        if not isinstance(answer, Mapping):
            raise ValueError("Jev decision answer must be an object")
        return answer


class SemanticClassifier(_PrimitiveEvaluator):
    """Turn text into a typed category using a Choice primitive."""

    def __init__(self, definition: DecisionDefinition, runtime: Any):
        if not isinstance(definition, DecisionDefinition):
            raise TypeError("definition must be a DecisionDefinition")
        if definition.kind != "classifier":
            raise TypeError("SemanticClassifier requires a classifier definition")
        super().__init__(name=definition.name, runtime=runtime)
        self.definition = definition

    @classmethod
    def from_definition(
        cls,
        definition: DecisionDefinition,
        *,
        runtime: Any,
    ) -> "SemanticClassifier":
        return cls(definition, runtime)

    def classify(self, text: str) -> ClassificationResult:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("classification text must be a non-empty string")
        answer = self._execute(
            {self.definition.input_field: text},
            {
                "type": "choice",
                "instructions": self._instructions(),
                "criteria": {
                    value: category.description
                    for value, category in self.definition.categories.items()
                },
            },
        )
        selected = answer.get("choice", answer.get("selected", answer.get("value")))
        if not isinstance(selected, str) or not selected:
            raise ValueError("Jev response does not contain a selected category")
        category = self.definition.categories.get(selected)
        if category is None:
            raise ValueError(f"unknown category returned by Jev: {selected}")

        probabilities = _probabilities(answer)
        confidence = _confidence(answer, probabilities)
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


class ScoreEvaluator(_PrimitiveEvaluator):
    """Evaluate a state with a Score primitive."""

    def __init__(
        self,
        *,
        name: str,
        criteria: Sequence[Any],
        runtime: Any,
        instructions: str | None = None,
        input_field: str | None = None,
    ) -> None:
        if isinstance(criteria, (str, bytes)) or not isinstance(criteria, Sequence):
            raise TypeError("score criteria must be a sequence")
        if not criteria:
            raise ValueError("score criteria must not be empty")
        super().__init__(
            name=name,
            runtime=runtime,
            instructions=instructions,
            input_field=input_field,
        )
        self.criteria = list(criteria)

    @classmethod
    def from_definition(
        cls,
        definition: DecisionDefinition,
        *,
        runtime: Any,
    ) -> "ScoreEvaluator":
        if not isinstance(definition, DecisionDefinition):
            raise TypeError("definition must be a DecisionDefinition")
        if definition.kind != "score":
            raise TypeError("ScoreEvaluator requires a score definition")
        return cls(
            name=definition.name,
            criteria=definition.criteria,
            runtime=runtime,
            instructions=definition.instructions,
            input_field=definition.input_field,
        )

    def evaluate(self, state: Any) -> ScoreResult:
        question: dict[str, Any] = {
            "type": "score",
            "criteria": self.criteria,
        }
        if self.instructions is not None:
            question["instructions"] = self.instructions
        answer = self._execute(self._prepare_state(state), question)
        score = answer.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError("Jev score answer must contain a number")
        probabilities = _probabilities(answer)
        return ScoreResult(
            score=float(score),
            confidence=_confidence(answer, probabilities),
            legend=answer.get("legend"),
            probabilities=probabilities,
        )


class NoulEvaluator(_PrimitiveEvaluator):
    """Evaluate a state with a Noul probability primitive."""

    def __init__(
        self,
        *,
        name: str,
        runtime: Any,
        criteria: Any = None,
        instructions: str | None = None,
        input_field: str | None = None,
    ) -> None:
        super().__init__(
            name=name,
            runtime=runtime,
            instructions=instructions,
            input_field=input_field,
        )
        self.criteria = criteria

    @classmethod
    def from_definition(
        cls,
        definition: DecisionDefinition,
        *,
        runtime: Any,
    ) -> "NoulEvaluator":
        if not isinstance(definition, DecisionDefinition):
            raise TypeError("definition must be a DecisionDefinition")
        if definition.kind != "noul":
            raise TypeError("NoulEvaluator requires a noul definition")
        return cls(
            name=definition.name,
            criteria=definition.criteria,
            runtime=runtime,
            instructions=definition.instructions,
            input_field=definition.input_field,
        )

    def evaluate(self, state: Any) -> NoulResult:
        question: dict[str, Any] = {"type": "noul"}
        if self.instructions is not None:
            question["instructions"] = self.instructions
        if self.criteria is not None:
            question["criteria"] = self.criteria
        answer = self._execute(self._prepare_state(state), question)
        probability = answer.get("noul", answer.get("probability"))
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise ValueError("Jev Noul answer must contain a probability")
        return NoulResult(probability=float(probability))


def _probabilities(answer: Mapping[str, Any]) -> Mapping[str, float] | None:
    probabilities = answer.get("probabilities")
    if probabilities is None:
        return None
    if not isinstance(probabilities, Mapping):
        raise ValueError("Jev probabilities must be an object")
    return {str(key): float(value) for key, value in probabilities.items()}


def _confidence(
    answer: Mapping[str, Any],
    probabilities: Mapping[str, float] | None,
) -> float:
    confidence = answer.get("confidence")
    if confidence is None and probabilities:
        confidence = max(probabilities.values())
    if confidence is None:
        confidence = 0.0
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("Jev confidence must be a number")
    if not 0 <= confidence <= 1:
        raise ValueError("Jev confidence must be between 0 and 1")
    return float(confidence)
