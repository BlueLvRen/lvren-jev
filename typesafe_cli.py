from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from typesafe_client import DEFAULT_CONFIG_PATH, JevService, error_payload, load_config


def parse_state(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def parse_questions(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"questions must be valid JSON: {error.msg}") from error
    if not isinstance(parsed, Mapping):
        raise ValueError("questions must be a JSON object")
    return dict(parsed)


def _read_argument(value: str | None, file_path: str | None, name: str) -> str:
    if bool(value) == bool(file_path):
        raise ValueError(f"provide exactly one of --{name} and --{name}-file")
    if file_path:
        return Path(file_path).read_text(encoding="utf-8")
    assert value is not None
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Call TypeSafe Jev and print typed answers as JSON."
    )
    state = parser.add_mutually_exclusive_group(required=True)
    state.add_argument("--state", help="State as JSON, or plain text if JSON parsing fails")
    state.add_argument("--state-file", help="UTF-8 file containing JSON or plain-text state")
    questions = parser.add_mutually_exclusive_group(required=True)
    questions.add_argument("--questions", help="Questions definition as a JSON object")
    questions.add_argument("--questions-file", help="UTF-8 file containing a questions JSON object")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Path to the main TOML config (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--profile",
        help="Select a profile from [typesafe.profiles]",
    )
    parser.add_argument("--model", help="Override the model configured in TOML")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    return parser


def _exit_code(status: int) -> int:
    if status == 400:
        return 2
    if status >= 500 or status == 429:
        return 3
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        state_text = _read_argument(args.state, args.state_file, "state")
        questions_text = _read_argument(args.questions, args.questions_file, "questions")
        payload = {
            "state": parse_state(state_text),
            "questions": parse_questions(questions_text),
        }
        config = load_config(args.config, profile=args.profile)
        with JevService(config) as service:
            result = service.evaluate(payload, model=args.model)
        output = result
        status = 200
    except Exception as error:
        status, output = error_payload(error)

    indent = 2 if args.pretty else None
    print(json.dumps(output, ensure_ascii=False, indent=indent))
    return 0 if status == 200 else _exit_code(status)


if __name__ == "__main__":
    sys.exit(main())
