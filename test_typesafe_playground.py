import json
import tempfile
import unittest
from pathlib import Path

from typesafe_cli import parse_questions, parse_state
from typesafe_client import (
    JevService,
    TypeSafeConfig,
    build_questions,
    error_payload,
    evaluate_request,
    load_config,
)


class FakeAnswer:
    def __init__(self, value):
        self.value = value

    def model_dump(self):
        return self.value


class FakeResponse:
    def __init__(self):
        self.answers = {
            "team": FakeAnswer(
                {
                    "type": "choice",
                    "choice": "billing",
                    "confidence": 0.9,
                    "probabilities": {"billing": 0.9, "other": 0.1},
                }
            ),
            "urgency": FakeAnswer(
                {
                    "type": "score",
                    "score": 1.2,
                    "confidence": 0.8,
                    "probabilities": {"0": 0.1, "1": 0.8, "2": 0.1},
                }
            ),
            "urgent": FakeAnswer({"type": "noul", "noul": 0.8}),
        }


class FakeClient:
    def __init__(self):
        self.calls = []

    def system_one(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse()


class JevPlaygroundTests(unittest.TestCase):
    def test_load_config_reads_api_key_base_url_and_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "typesafe.toml"
            path.write_text(
                '[typesafe]\napi_key = "key"\n'
                'base_url = "https://example.test"\n'
                'model = "jev-test"\n',
                encoding="utf-8",
            )

            config = load_config(path)

        self.assertEqual(
            config,
            TypeSafeConfig(
                api_key="key",
                base_url="https://example.test",
                model="jev-test",
            ),
        )

    def test_load_config_reads_api_key_from_referenced_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "typesafe.toml").write_text(
                '[typesafe]\napi_key_file = "typesafe.secrets.toml"\n'
                'base_url = "https://example.test"\nmodel = "jev-test"\n',
                encoding="utf-8",
            )
            (root / "typesafe.secrets.toml").write_text(
                '[typesafe]\napi_key = "migrated-key"\n',
                encoding="utf-8",
            )

            config = load_config(root / "typesafe.toml")

        self.assertEqual(config.api_key, "migrated-key")

    def test_load_config_rejects_inline_key_and_key_file_together(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "typesafe.toml"
            path.write_text(
                '[typesafe]\napi_key = "inline"\n'
                'api_key_file = "typesafe.secrets.toml"\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "not both"):
                load_config(path)

    def test_load_config_selects_default_and_explicit_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "typesafe.toml").write_text(
                '[typesafe]\ndefault_profile = "official"\n'
                '[typesafe.profiles.official]\n'
                'api_key_file = "official.toml"\n'
                'base_url = "https://official.test"\nmodel = "jev-official"\n'
                '[typesafe.profiles.partner]\n'
                'api_key_file = "partner.toml"\n'
                'base_url = "https://partner.test"\nmodel = "jev-partner"\n',
                encoding="utf-8",
            )
            (root / "official.toml").write_text(
                '[typesafe]\napi_key = "official-key"\n',
                encoding="utf-8",
            )
            (root / "partner.toml").write_text(
                '[typesafe]\napi_key = "partner-key"\n',
                encoding="utf-8",
            )

            default_config = load_config(root / "typesafe.toml")
            partner_config = load_config(root / "typesafe.toml", profile="partner")

        self.assertEqual(default_config.profile, "official")
        self.assertEqual(default_config.base_url, "https://official.test")
        self.assertEqual(partner_config.profile, "partner")
        self.assertEqual(partner_config.api_key, "partner-key")

    def test_load_config_rejects_unknown_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "typesafe.toml"
            path.write_text(
                '[typesafe]\ndefault_profile = "official"\n'
                '[typesafe.profiles.official]\n'
                'api_key = "key"\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Unknown TypeSafe profile"):
                load_config(path, profile="missing")

    def test_build_questions_supports_choice_score_and_noul(self):
        questions = build_questions(
            {
                "team": {
                    "type": "choice",
                    "instructions": "Which team?",
                    "criteria": {"billing": "Payments", "other": None},
                },
                "urgency": {
                    "type": "score",
                    "instructions": "How urgent?",
                    "criteria": ["Can wait", "Today"],
                },
                "urgent": {
                    "type": "noul",
                    "instructions": "Is it urgent?",
                },
            }
        )

        self.assertEqual(type(questions["team"]).__name__, "Choice")
        self.assertEqual(type(questions["urgency"]).__name__, "Score")
        self.assertEqual(type(questions["urgent"]).__name__, "Noul")

    def test_build_questions_rejects_empty_score_level(self):
        with self.assertRaisesRegex(ValueError, "non-empty strings"):
            build_questions(
                {
                    "urgency": {
                        "type": "score",
                        "instructions": "How urgent?",
                        "criteria": ["Can wait", ""],
                    }
                }
            )

    def test_build_questions_rejects_invalid_noul_criteria(self):
        with self.assertRaisesRegex(ValueError, "true.*false"):
            build_questions(
                {
                    "urgent": {
                        "type": "noul",
                        "instructions": "Is it urgent?",
                        "criteria": {"maybe": "unknown"},
                    }
                }
            )

    def test_evaluate_request_returns_answers_and_elapsed_time(self):
        client = FakeClient()
        result = evaluate_request(
            {
                "state": {"message": "Please help"},
                "questions": {
                    "urgent": {
                        "type": "noul",
                        "instructions": "Is it urgent?",
                    }
                },
            },
            client=client,
            config=TypeSafeConfig("key", "https://example.test", "jev-test"),
            model="jev-test",
        )

        self.assertGreaterEqual(result["elapsed_ms"], 0)
        self.assertGreaterEqual(result["timing"]["jev_call_ms"], 0)
        self.assertEqual(result["answers"]["team"]["choice"], "billing")
        self.assertEqual(result["answers"]["team"]["confidence"], 0.9)
        self.assertEqual(result["profile"], "default")
        self.assertEqual(result["base_url"], "https://example.test")
        self.assertEqual(client.calls[0]["model"], "jev-test")
        json.dumps(result)

    def test_service_reuses_one_client_for_multiple_requests(self):
        client = FakeClient()
        service = JevService(
            TypeSafeConfig("key", "https://example.test", "jev-test"),
            client=client,
        )

        service.evaluate({"state": "one", "questions": {"urgent": {"type": "noul", "instructions": "Is it urgent?"}}})
        service.evaluate({"state": "two", "questions": {"urgent": {"type": "noul", "instructions": "Is it urgent?"}}})

        self.assertEqual(len(client.calls), 2)

    def test_error_payload_has_stable_code_and_message(self):
        status, payload = error_payload(ValueError("bad request"))

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "INVALID_REQUEST")
        self.assertEqual(payload["error"]["message"], "bad request")

    def test_cli_parses_json_state_and_plain_text_state(self):
        self.assertEqual(parse_state('{"message":"hello"}'), {"message": "hello"})
        self.assertEqual(parse_state("plain text state"), "plain text state")

    def test_cli_requires_questions_to_be_a_json_object(self):
        with self.assertRaisesRegex(ValueError, "questions must be a JSON object"):
            parse_questions("[1, 2]")

    def test_cli_accepts_profile_argument(self):
        from typesafe_cli import build_parser

        args = build_parser().parse_args(
            ["--state", "text", "--questions", "{}", "--profile", "partner"]
        )

        self.assertEqual(args.profile, "partner")


if __name__ == "__main__":
    unittest.main()
