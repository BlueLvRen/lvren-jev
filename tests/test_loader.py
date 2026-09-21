import json
import tempfile
import unittest
from pathlib import Path

from lvren_jev import (
    CategoryDefinition,
    DefinitionError,
    DecisionDefinition,
    DecisionPolicy,
    load_decision_definition,
)


class DecisionDefinitionLoaderTests(unittest.TestCase):
    def test_loads_yaml_into_validated_definition(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decision.yaml"
            path.write_text(
                """
version: 1
kind: classifier
name: ticket_classifier
input:
  type: text
  field: description
categories:
  incident:
    label: Incident
    description: Production failure or outage
  feature:
    label: Feature
    description: New product capability
policy:
  threshold: 0.65
  fallback:
    value: pending
    label: Pending review
""",
                encoding="utf-8",
            )

            definition = load_decision_definition(path)

        self.assertEqual(definition.name, "ticket_classifier")
        self.assertEqual(definition.input_field, "description")
        self.assertEqual(definition.categories["incident"].label, "Incident")
        self.assertEqual(definition.policy.threshold, 0.65)
        self.assertEqual(definition.policy.fallback.value, "pending")

    def test_loads_json_with_the_same_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decision.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "kind": "classifier",
                        "name": "simple",
                        "categories": {
                            "yes": {"label": "Yes", "description": "Affirmative"},
                            "no": {"label": "No", "description": "Negative"},
                        },
                        "policy": {
                            "threshold": 0.5,
                            "fallback": {"value": "unknown", "label": "Unknown"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            definition = load_decision_definition(path)

            self.assertEqual(definition.categories["yes"].description, "Affirmative")

    def test_loads_score_definition(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "risk_score.yaml"
            path.write_text(
                """
version: 1
kind: score
name: risk_score
input:
  type: text
  field: description
  instructions: Score the operational risk from 0 to 5.
criteria:
  - 0 = low risk
  - 5 = high risk
""",
                encoding="utf-8",
            )

            definition = load_decision_definition(path)

            self.assertEqual(definition.kind, "score")
            self.assertEqual(definition.criteria, ["0 = low risk", "5 = high risk"])
            self.assertIsNone(definition.categories)
            self.assertIsNone(definition.policy)

    def test_loads_noul_definition(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "needs_review.yaml"
            path.write_text(
                """
version: 1
kind: noul
name: needs_review
input:
  type: text
  field: description
criteria:
  true: The case requires human review.
  false: The case does not require human review.
""",
                encoding="utf-8",
            )

            definition = load_decision_definition(path)

            self.assertEqual(definition.kind, "noul")
            self.assertEqual(
                definition.criteria,
                {
                    "true": "The case requires human review.",
                    "false": "The case does not require human review.",
                },
            )
            self.assertIsNone(definition.categories)
            self.assertIsNone(definition.policy)

    def test_loads_all_repository_primitive_examples(self):
        repository_root = Path(__file__).parents[1]
        examples = {
            "classifier": repository_root / "examples" / "worklog_classifier" / "worklog.yaml",
            "score": repository_root / "examples" / "score_evaluator" / "risk_score.yaml",
            "noul": repository_root / "examples" / "noul_evaluator" / "needs_review.yaml",
        }

        for kind, path in examples.items():
            with self.subTest(kind=kind):
                self.assertEqual(load_decision_definition(path).kind, kind)

    def test_rejects_unsupported_kind_and_invalid_threshold(self):
        with self.assertRaises(DefinitionError):
            DecisionDefinition.from_mapping(
                {
                    "version": 1,
                    "kind": "router",
                    "name": "bad",
                    "categories": {"a": {"label": "A", "description": "A"}},
                    "policy": {
                        "threshold": 0.5,
                        "fallback": {"value": "unknown", "label": "Unknown"},
                    },
                }
            )

        with self.assertRaises(DefinitionError):
            DecisionDefinition(
                name="bad",
                categories={"a": CategoryDefinition("a", "A", "A")},
                policy=DecisionPolicy(threshold=1.1),
            )


if __name__ == "__main__":
    unittest.main()
