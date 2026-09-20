from __future__ import annotations

import dataclasses
import json
import time
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path(__file__).with_name("typesafe.toml")
DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-latest"
DEFAULT_MAX_QUESTIONS = 0


@dataclass(frozen=True)
class TypeSafeConfig:
    api_key: str
    base_url: str
    model: str
    profile: str = "default"
    max_questions: int = DEFAULT_MAX_QUESTIONS


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as config_file:
        return tomllib.load(config_file)


def _read_max_questions(raw_config: Mapping[str, Any], config_path: Path) -> int:
    runtime = raw_config.get("runtime", {})
    if not isinstance(runtime, Mapping):
        raise ValueError(f"[runtime] must be an object in {config_path}")

    max_questions = runtime.get("max_questions", DEFAULT_MAX_QUESTIONS)
    if isinstance(max_questions, bool) or not isinstance(max_questions, int) or max_questions < 0:
        raise ValueError(
            f"[runtime].max_questions must be a non-negative integer in {config_path}"
        )
    return max_questions


def _read_api_key(config_path: Path, typesafe: Mapping[str, Any]) -> str | None:
    inline_key = typesafe.get("api_key")
    key_file = typesafe.get("api_key_file")
    if inline_key and key_file:
        raise ValueError(
            f"[typesafe] must use api_key or api_key_file, not both, in {config_path}"
        )

    if key_file:
        if not isinstance(key_file, str) or not key_file.strip():
            raise ValueError(f"api_key_file must be a non-empty string in {config_path}")
        secret_path = Path(key_file)
        if not secret_path.is_absolute():
            secret_path = config_path.parent / secret_path
        if not secret_path.is_file():
            raise FileNotFoundError(f"Missing API key file: {secret_path}")
        secret_config = _read_toml(secret_path)
        secret_typesafe = secret_config.get("typesafe")
        if not isinstance(secret_typesafe, Mapping):
            raise ValueError(f"Missing [typesafe] section in {secret_path}")
        inline_key = secret_typesafe.get("api_key")

    if inline_key is None:
        return None
    if not isinstance(inline_key, str) or not inline_key.strip():
        raise ValueError(f"api_key must be a non-empty string in {config_path}")
    return inline_key.strip()


def _select_profile(
    config_path: Path,
    typesafe: Mapping[str, Any],
    profile: str | None,
) -> tuple[str, Mapping[str, Any]]:
    profiles = typesafe.get("profiles")
    if profiles is None:
        return "default", typesafe
    if not isinstance(profiles, Mapping) or not profiles:
        raise ValueError(f"[typesafe.profiles] must be a non-empty object in {config_path}")

    selected = profile or typesafe.get("default_profile")
    if not isinstance(selected, str) or not selected.strip():
        raise ValueError(
            f"Set [typesafe].default_profile or pass an explicit profile for {config_path}"
        )
    selected = selected.strip()
    selected_config = profiles.get(selected)
    if not isinstance(selected_config, Mapping):
        available = ", ".join(str(name) for name in profiles)
        raise ValueError(
            f"Unknown TypeSafe profile '{selected}' in {config_path}; available: {available}"
        )
    return selected, selected_config


def load_config(
    path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    profile: str | None = None,
) -> TypeSafeConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Missing TypeSafe configuration: {config_path}. "
            "Create it with [typesafe]."
        )

    raw_config = _read_toml(config_path)
    max_questions = _read_max_questions(raw_config, config_path)
    typesafe = raw_config.get("typesafe")
    if not isinstance(typesafe, Mapping):
        raise ValueError(f"Missing [typesafe] section in {config_path}")

    selected_profile, selected_config = _select_profile(config_path, typesafe, profile)
    api_key = _read_api_key(config_path, selected_config)
    base_url = selected_config.get("base_url", DEFAULT_BASE_URL)
    model = selected_config.get("model", DEFAULT_MODEL)
    missing = [
        name
        for name, value in (("api_key", api_key), ("base_url", base_url), ("model", model))
        if not isinstance(value, str) or not value.strip()
    ]
    if missing:
        raise ValueError(
            f"Missing [typesafe] field(s) in {config_path}: {', '.join(missing)}"
        )

    return TypeSafeConfig(
        api_key=api_key,
        base_url=base_url.strip().rstrip("/"),
        model=model.strip(),
        profile=selected_profile,
        max_questions=max_questions,
    )


def create_client(config: TypeSafeConfig | None = None):
    from typesafe_sdk import TypeSafeClient

    resolved = config or load_config()
    return TypeSafeClient(base_url=resolved.base_url, api_key=resolved.api_key)


def _is_json_value(value: Any) -> bool:
    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return False
    return isinstance(value, (str, int, float, bool, type(None), Mapping, list, tuple))


def _validate_instruction(name: str, instructions: Any) -> Any:
    if instructions is None:
        raise ValueError(f"question '{name}' needs non-empty instructions")
    if isinstance(instructions, str) and not instructions.strip():
        raise ValueError(f"question '{name}' needs non-empty instructions")
    if isinstance(instructions, (Mapping, list, tuple)) and not instructions:
        raise ValueError(f"question '{name}' needs non-empty instructions")
    if not _is_json_value(instructions):
        raise ValueError(f"question '{name}' instructions must be JSON-compatible")
    return instructions


def _validate_criteria_value(name: str, value: Any) -> None:
    if not _is_json_value(value):
        raise ValueError(f"question '{name}' criteria values must be JSON-compatible")


def build_questions(
    specs: Mapping[str, Mapping[str, Any]],
    *,
    max_questions: int = DEFAULT_MAX_QUESTIONS,
) -> dict[str, Any]:
    if not isinstance(specs, Mapping) or not specs:
        raise ValueError("questions must be a non-empty object")
    if isinstance(max_questions, bool) or not isinstance(max_questions, int) or max_questions < 0:
        raise ValueError("max_questions must be a non-negative integer")
    if max_questions > 0 and len(specs) > max_questions:
        raise ValueError(f"a request can contain at most {max_questions} questions")

    from typesafe_sdk import Choice, Noul, Score

    questions: dict[str, Any] = {}
    for raw_name, spec in specs.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError("question names must be non-empty strings")
        name = raw_name.strip()
        if name in questions:
            raise ValueError(f"duplicate question name: {name}")
        if not isinstance(spec, Mapping):
            raise ValueError(f"question '{name}' must be an object")

        question_type = spec.get("type")
        instructions = _validate_instruction(name, spec.get("instructions"))

        if question_type == "choice":
            criteria = spec.get("criteria")
            if not isinstance(criteria, Mapping) or not criteria:
                raise ValueError(f"choice question '{name}' needs a criteria object")
            normalized_criteria: dict[str, Any] = {}
            for raw_label, description in criteria.items():
                if not isinstance(raw_label, str) or not raw_label.strip():
                    raise ValueError(
                        f"choice question '{name}' criteria labels must be non-empty strings"
                    )
                label = raw_label.strip()
                if label in normalized_criteria:
                    raise ValueError(f"choice question '{name}' has duplicate label: {label}")
                _validate_criteria_value(name, description)
                normalized_criteria[label] = description
            questions[name] = Choice(
                instructions=instructions,
                criteria=normalized_criteria,
            )
        elif question_type == "score":
            criteria = spec.get("criteria")
            if not isinstance(criteria, list) or len(criteria) < 2:
                raise ValueError(f"score question '{name}' needs at least two criteria")
            seen: set[str] = set()
            normalized_criteria: list[Any] = []
            for level in criteria:
                if isinstance(level, str):
                    if not level.strip():
                        raise ValueError(
                            f"score question '{name}' criteria must be non-empty strings"
                        )
                    marker = f"str:{level.strip()}"
                    normalized_level: Any = level.strip()
                else:
                    if not _is_json_value(level):
                        raise ValueError(
                            f"score question '{name}' criteria must be JSON-compatible"
                        )
                    marker = json.dumps(level, ensure_ascii=False, sort_keys=True)
                    normalized_level = level
                if marker in seen:
                    raise ValueError(f"score question '{name}' criteria must be unique")
                seen.add(marker)
                normalized_criteria.append(normalized_level)
            questions[name] = Score(
                instructions=instructions,
                criteria=normalized_criteria,
            )
        elif question_type == "noul":
            criteria = spec.get("criteria")
            if criteria is not None:
                if not isinstance(criteria, Mapping) or not set(criteria).issubset({"true", "false"}):
                    raise ValueError(
                        f"noul question '{name}' criteria keys must be true and/or false"
                    )
                for description in criteria.values():
                    _validate_criteria_value(name, description)
                questions[name] = Noul(
                    instructions=instructions,
                    criteria=dict(criteria),
                )
            else:
                questions[name] = Noul(instructions=instructions)
        else:
            raise ValueError(f"unsupported question type for '{name}': {question_type!r}")

    return questions


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    if dataclasses.is_dataclass(value):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def serialize_response(response: Any) -> dict[str, Any]:
    answers = getattr(response, "answers", None)
    if answers is None:
        answers = {}
        for group_name in ("choices", "scores", "nouls"):
            group = getattr(response, group_name, {}) or {}
            answers.update(group)
    result = {"answers": _jsonable(answers)}
    usage = getattr(response, "usage", None)
    if usage is not None:
        result["usage"] = _jsonable(usage)
    return result


def _validate_state(state: Any) -> None:
    if state is None:
        raise ValueError("state is required")
    if not _is_json_value(state):
        raise ValueError("state must be a string, array, or JSON object")


def evaluate_request(
    payload: Mapping[str, Any],
    *,
    client: Any | None = None,
    config: TypeSafeConfig | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("request body must be a JSON object")

    total_started = time.perf_counter_ns()
    state = payload.get("state")
    _validate_state(state)

    config_started = time.perf_counter_ns()
    resolved_config = config or load_config()
    resolved_model = model or resolved_config.model
    config_ms = round((time.perf_counter_ns() - config_started) / 1_000_000, 2)

    questions_started = time.perf_counter_ns()
    questions = build_questions(
        payload.get("questions", {}),
        max_questions=resolved_config.max_questions,
    )
    questions_ms = round((time.perf_counter_ns() - questions_started) / 1_000_000, 2)

    owns_client = client is None
    client_started = time.perf_counter_ns()
    resolved_client = client or create_client(resolved_config)
    client_setup_ms = round((time.perf_counter_ns() - client_started) / 1_000_000, 2)

    try:
        jev_started = time.perf_counter_ns()
        response = resolved_client.system_one(
            state=state,
            model=resolved_model,
            questions=questions,
        )
        jev_call_ms = round((time.perf_counter_ns() - jev_started) / 1_000_000, 2)

        serialization_started = time.perf_counter_ns()
        result = serialize_response(response)
        serialization_ms = round(
            (time.perf_counter_ns() - serialization_started) / 1_000_000,
            2,
        )
    finally:
        if owns_client and hasattr(resolved_client, "close"):
            resolved_client.close()

    total_ms = round((time.perf_counter_ns() - total_started) / 1_000_000, 2)
    result["model"] = resolved_model
    result["profile"] = resolved_config.profile
    result["base_url"] = resolved_config.base_url
    result["elapsed_ms"] = total_ms
    result["timing"] = {
        "total_ms": total_ms,
        "config_ms": config_ms,
        "client_setup_ms": client_setup_ms,
        "question_build_ms": questions_ms,
        "jev_call_ms": jev_call_ms,
        "serialization_ms": serialization_ms,
    }
    return result


class JevService:
    """Own one reusable TypeSafe client for a server or CLI process."""

    def __init__(self, config: TypeSafeConfig | None = None, *, client: Any | None = None):
        self.config = config or load_config()
        self.client = client or create_client(self.config)
        self._owns_client = client is None

    def evaluate(self, payload: Mapping[str, Any], *, model: str | None = None) -> dict[str, Any]:
        return evaluate_request(
            payload,
            client=self.client,
            config=self.config,
            model=model,
        )

    def close(self) -> None:
        if self._owns_client and hasattr(self.client, "close"):
            self.client.close()
            self._owns_client = False

    def __enter__(self) -> "JevService":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()


def error_payload(error: Exception) -> tuple[int, dict[str, Any]]:
    error_name = type(error).__name__.lower()
    if isinstance(error, (ValueError, TypeError)):
        status, code = 400, "INVALID_REQUEST"
    elif isinstance(error, FileNotFoundError) or isinstance(error, PermissionError):
        status, code = 500, "CONFIG_ERROR"
    elif "authentication" in error_name or "permissiondenied" in error_name:
        status, code = 502, "TYPESAFE_AUTHENTICATION_ERROR"
    elif "timeout" in error_name:
        status, code = 504, "TYPESAFE_TIMEOUT"
    elif "ratelimit" in error_name:
        status, code = 429, "TYPESAFE_RATE_LIMIT"
    elif "api" in error_name or "connection" in error_name:
        status, code = 502, "TYPESAFE_API_ERROR"
    else:
        status, code = 500, "INTERNAL_ERROR"
    return status, {"error": {"code": code, "message": str(error)}}
