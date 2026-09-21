from __future__ import annotations

import dataclasses
import hashlib
import json
import time
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .errors import JevRuntimeError


@dataclass(frozen=True)
class DecisionRequest:
    state: Any
    questions: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class JevResponse:
    answers: Mapping[str, Any]
    usage: Any = None
    model: str | None = None
    raw: Any = field(default=None, repr=False, compare=False)


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


def normalize_response(response: Any) -> JevResponse:
    answers = response.get("answers") if isinstance(response, Mapping) else getattr(response, "answers", None)
    if answers is None:
        answers = {}
    if not isinstance(answers, Mapping):
        raise JevRuntimeError("INVALID_RESPONSE", "Jev response answers must be an object")
    usage = response.get("usage") if isinstance(response, Mapping) else getattr(response, "usage", None)
    model = response.get("model") if isinstance(response, Mapping) else getattr(response, "model", None)
    return JevResponse(
        answers=_jsonable(answers),
        usage=_jsonable(usage),
        model=model,
        raw=response,
    )


@dataclass(frozen=True)
class _RuntimeConfig:
    api_key: str | None
    base_url: str
    model: str
    timeout: float | None
    retry: int
    cache: bool


class JevRuntime:
    """Reusable, business-neutral execution infrastructure for Jev decisions."""

    def __init__(
        self,
        client: Any,
        *,
        model: str = "jev-latest",
        timeout: float | None = 30.0,
        retry: int = 0,
        cache: bool = False,
        telemetry: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> None:
        if not model or not isinstance(model, str):
            raise ValueError("model must be a non-empty string")
        if timeout is not None and (isinstance(timeout, bool) or timeout <= 0):
            raise ValueError("timeout must be positive or None")
        if isinstance(retry, bool) or not isinstance(retry, int) or retry < 0:
            raise ValueError("retry must be a non-negative integer")
        self.client = client
        self.model = model
        self.timeout = timeout
        self.retry = retry
        self.cache_enabled = cache
        self.telemetry = telemetry
        self.metrics: list[dict[str, Any]] = []
        self._cache: dict[str, JevResponse] = {}

    @classmethod
    def from_config(
        cls,
        path: str | Path,
        *,
        profile: str | None = None,
        client: Any | None = None,
        telemetry: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> "JevRuntime":
        config = _load_runtime_config(Path(path), profile=profile)
        resolved_client = client
        if resolved_client is None:
            if not config.api_key:
                raise ValueError("missing API key in runtime configuration")
            from typesafe_sdk import TypeSafeClient

            resolved_client = TypeSafeClient(
                base_url=config.base_url,
                api_key=config.api_key,
                timeout=config.timeout,
            )
        return cls(
            resolved_client,
            model=config.model,
            timeout=config.timeout,
            retry=config.retry,
            cache=config.cache,
            telemetry=telemetry,
        )

    def execute(self, request: DecisionRequest) -> JevResponse:
        if not isinstance(request, DecisionRequest):
            raise TypeError("request must be a DecisionRequest")
        cache_key = self._cache_key(request)
        if self.cache_enabled and cache_key in self._cache:
            return self._cache[cache_key]

        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(self.retry + 1):
            try:
                kwargs: dict[str, Any] = {
                    "state": request.state,
                    "model": self.model,
                    "questions": request.questions,
                }
                if self.timeout is not None:
                    kwargs["timeout"] = self.timeout
                response = normalize_response(self.client.system_one(**kwargs))
                elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
                metric = {"elapsed_ms": elapsed_ms, "attempt": attempt + 1, "cached": False}
                self.metrics.append(metric)
                if self.telemetry is not None:
                    self.telemetry(metric)
                if self.cache_enabled:
                    self._cache[cache_key] = response
                return response
            except JevRuntimeError:
                raise
            except Exception as error:
                last_error = error
                if attempt >= self.retry or not _is_retryable(error):
                    raise _runtime_error(error) from error
        raise _runtime_error(last_error or RuntimeError("unknown Jev runtime failure"))

    def close(self) -> None:
        if hasattr(self.client, "close"):
            self.client.close()

    def __enter__(self) -> "JevRuntime":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    @staticmethod
    def _cache_key(request: DecisionRequest) -> str:
        payload = json.dumps(
            {"state": request.state, "questions": request.questions},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_retryable(error: Exception) -> bool:
    name = type(error).__name__.lower()
    return isinstance(error, (TimeoutError, ConnectionError)) or "timeout" in name or "connection" in name


def _runtime_error(error: Exception) -> JevRuntimeError:
    name = type(error).__name__.lower()
    message = str(error)
    if "authentication" in name or "permission" in name or "unauthorized" in name:
        code = "AUTHENTICATION_ERROR"
    elif "ratelimit" in name or "rate_limit" in name:
        code = "RATE_LIMIT"
    elif "timeout" in name:
        code = "TIMEOUT"
    elif "connection" in name or "api" in name or isinstance(error, ConnectionError):
        code = "API_ERROR"
    else:
        code = "API_ERROR"
    return JevRuntimeError(code, message, cause=error)


def _load_runtime_config(path: Path, *, profile: str | None) -> _RuntimeConfig:
    if not path.is_file():
        raise FileNotFoundError(f"runtime configuration does not exist: {path}")
    with path.open("rb") as config_file:
        raw = tomllib.load(config_file)
    typesafe = raw.get("typesafe")
    if not isinstance(typesafe, Mapping):
        raise ValueError(f"missing [typesafe] section in {path}")
    profiles = typesafe.get("profiles")
    if profiles is not None:
        if not isinstance(profiles, Mapping):
            raise ValueError(f"[typesafe.profiles] must be an object in {path}")
        selected_name = profile or typesafe.get("default_profile")
        if not isinstance(selected_name, str) or selected_name not in profiles:
            raise ValueError(f"unknown runtime profile: {selected_name!r}")
        selected = profiles[selected_name]
        if not isinstance(selected, Mapping):
            raise ValueError(f"runtime profile must be an object: {selected_name}")
    else:
        selected = typesafe

    api_key = selected.get("api_key")
    key_file = selected.get("api_key_file")
    if api_key and key_file:
        raise ValueError("runtime configuration cannot use api_key and api_key_file together")
    if key_file:
        secret_path = Path(key_file)
        if not secret_path.is_absolute():
            secret_path = path.parent / secret_path
        with secret_path.open("rb") as secret_file:
            secret = tomllib.load(secret_file)
        secret_typesafe = secret.get("typesafe")
        if not isinstance(secret_typesafe, Mapping):
            raise ValueError(f"missing [typesafe] section in {secret_path}")
        api_key = secret_typesafe.get("api_key")

    runtime = raw.get("runtime", {})
    if not isinstance(runtime, Mapping):
        raise ValueError(f"[runtime] must be an object in {path}")
    timeout = runtime.get("timeout", 30.0)
    retry = runtime.get("retry", 0)
    cache = runtime.get("cache", False)
    if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0):
        raise ValueError("runtime.timeout must be positive or null")
    if isinstance(retry, bool) or not isinstance(retry, int) or retry < 0:
        raise ValueError("runtime.retry must be a non-negative integer")
    if not isinstance(cache, bool):
        raise ValueError("runtime.cache must be a boolean")
    base_url = selected.get("base_url", "https://api.typesafe.ai")
    model = selected.get("model", "jev-latest")
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("runtime base_url must be a non-empty string")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("runtime model must be a non-empty string")
    if api_key is not None and (not isinstance(api_key, str) or not api_key.strip()):
        raise ValueError("runtime api_key must be a non-empty string")
    return _RuntimeConfig(
        api_key=api_key.strip() if isinstance(api_key, str) else None,
        base_url=base_url.strip().rstrip("/"),
        model=model.strip(),
        timeout=float(timeout) if timeout is not None else None,
        retry=retry,
        cache=cache,
    )
