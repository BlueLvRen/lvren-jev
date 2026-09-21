from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .errors import DefinitionError


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DefinitionError(f"{field_name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class CategoryDefinition:
    value: str
    label: str
    description: str

    def __post_init__(self) -> None:
        _required_text(self.value, "category value")
        _required_text(self.label, f"category '{self.value}' label")
        _required_text(self.description, f"category '{self.value}' description")


@dataclass(frozen=True)
class FallbackPolicy:
    value: str = "pending_review"
    label: str = "待确认"

    def __post_init__(self) -> None:
        _required_text(self.value, "fallback value")
        _required_text(self.label, "fallback label")


@dataclass(frozen=True)
class DecisionPolicy:
    threshold: float = 0.65
    fallback: FallbackPolicy = field(default_factory=FallbackPolicy)

    def __post_init__(self) -> None:
        if isinstance(self.threshold, bool) or not isinstance(self.threshold, (int, float)):
            raise DefinitionError("policy.threshold must be a number")
        if not 0 <= self.threshold <= 1:
            raise DefinitionError("policy.threshold must be between 0 and 1")
        if not isinstance(self.fallback, FallbackPolicy):
            raise DefinitionError("policy.fallback must be a FallbackPolicy")


@dataclass(frozen=True)
class DecisionDefinition:
    name: str
    categories: Mapping[str, CategoryDefinition] | None = None
    policy: DecisionPolicy | None = None
    version: int = 1
    kind: str = "classifier"
    input_field: str = "description"
    instructions: str = ""
    criteria: Any = None

    def __post_init__(self) -> None:
        _required_text(self.name, "name")
        if self.version != 1:
            raise DefinitionError("only definition version 1 is supported")
        if self.kind not in {"classifier", "score", "noul"}:
            raise DefinitionError(
                "definition kind must be one of 'classifier', 'score', or 'noul'"
            )
        _required_text(self.input_field, "input.field")
        if self.kind == "classifier":
            if not isinstance(self.categories, Mapping) or not self.categories:
                raise DefinitionError("categories must be a non-empty object")
            policy = self.policy if self.policy is not None else DecisionPolicy()
            if not isinstance(policy, DecisionPolicy):
                raise DefinitionError("policy must be a DecisionPolicy")
            object.__setattr__(self, "policy", policy)

            normalized: dict[str, CategoryDefinition] = {}
            for raw_value, category in self.categories.items():
                value = _required_text(raw_value, "category value")
                if not isinstance(category, CategoryDefinition):
                    raise DefinitionError(f"category '{value}' must be a CategoryDefinition")
                if category.value != value:
                    raise DefinitionError(
                        f"category '{value}' does not match its CategoryDefinition.value"
                    )
                if value in normalized:
                    raise DefinitionError(f"duplicate category value: {value}")
                normalized[value] = category
            object.__setattr__(self, "categories", normalized)
            return

        if self.categories is not None:
            raise DefinitionError(f"kind '{self.kind}' does not use categories")
        if self.policy is not None:
            raise DefinitionError(f"kind '{self.kind}' does not use policy")

        if self.kind == "score":
            if isinstance(self.criteria, (str, bytes)) or not isinstance(self.criteria, Sequence):
                raise DefinitionError("score criteria must be a non-empty array")
            if not self.criteria:
                raise DefinitionError("score criteria must be a non-empty array")
            object.__setattr__(self, "criteria", list(self.criteria))
        elif self.criteria is not None:
            if isinstance(self.criteria, str):
                if not self.criteria.strip():
                    raise DefinitionError("noul criteria must not be empty")
            elif isinstance(self.criteria, Mapping):
                if not self.criteria:
                    raise DefinitionError("noul criteria must not be empty")
                normalized_criteria: dict[str, Any] = {}
                for raw_key, description in self.criteria.items():
                    if raw_key is True:
                        key = "true"
                    elif raw_key is False:
                        key = "false"
                    elif isinstance(raw_key, str) and raw_key in {"true", "false"}:
                        key = raw_key
                    else:
                        raise DefinitionError("noul criteria keys must be true and false")
                    if key in normalized_criteria:
                        raise DefinitionError(f"duplicate noul criteria key: {key}")
                    normalized_criteria[key] = description
                object.__setattr__(self, "criteria", normalized_criteria)
            else:
                raise DefinitionError("noul criteria must be an object, string, or null")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "DecisionDefinition":
        if not isinstance(raw, Mapping):
            raise DefinitionError("decision definition must be an object")

        version = raw.get("version", 1)
        kind = raw.get("kind")
        name = raw.get("name")
        if version != 1:
            raise DefinitionError("only definition version 1 is supported")
        _required_text(name, "name")

        raw_input = raw.get("input", {})
        if raw_input is None:
            raw_input = {}
        if not isinstance(raw_input, Mapping):
            raise DefinitionError("input must be an object")
        input_type = raw_input.get("type", "text")
        if input_type != "text":
            raise DefinitionError("only input.type 'text' is supported")
        input_field = _required_text(raw_input.get("field", "description"), "input.field")
        instructions = raw_input.get("instructions", "")
        if not isinstance(instructions, str):
            raise DefinitionError("input.instructions must be a string")

        categories: dict[str, CategoryDefinition] | None = None
        policy: DecisionPolicy | None = None
        criteria = raw.get("criteria")
        if kind == "classifier":
            raw_categories = raw.get("categories")
            if not isinstance(raw_categories, Mapping) or not raw_categories:
                raise DefinitionError("categories must be a non-empty object")
            categories = {}
            for raw_value, raw_category in raw_categories.items():
                value = _required_text(raw_value, "category value")
                if not isinstance(raw_category, Mapping):
                    raise DefinitionError(f"category '{value}' must be an object")
                categories[value] = CategoryDefinition(
                    value=value,
                    label=_required_text(raw_category.get("label"), f"category '{value}' label"),
                    description=_required_text(
                        raw_category.get("description"),
                        f"category '{value}' description",
                    ),
                )

            raw_policy = raw.get("policy", {})
            if not isinstance(raw_policy, Mapping):
                raise DefinitionError("policy must be an object")
            raw_fallback = raw_policy.get("fallback", {})
            if not isinstance(raw_fallback, Mapping):
                raise DefinitionError("policy.fallback must be an object")
            fallback = FallbackPolicy(
                value=raw_fallback.get("value", "pending_review"),
                label=raw_fallback.get("label", "待确认"),
            )
            policy = DecisionPolicy(
                threshold=raw_policy.get("threshold", 0.65),
                fallback=fallback,
            )
        elif kind not in {"score", "noul"}:
            raise DefinitionError(
                "definition kind must be one of 'classifier', 'score', or 'noul'"
            )
        return cls(
            version=version,
            kind=kind,
            name=name,
            input_field=input_field,
            instructions=instructions.strip(),
            categories=categories,
            policy=policy,
            criteria=criteria,
        )
