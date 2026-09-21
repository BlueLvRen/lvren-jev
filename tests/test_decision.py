import unittest

from lvren_jev import (
    DecisionDefinition,
    NoulEvaluator,
    NoulResult,
    ScoreEvaluator,
    ScoreResult,
    SemanticClassifier,
)
from lvren_jev.classifier import SemanticClassifier as LegacySemanticClassifier
from lvren_jev.decision import SemanticClassifier as DecisionSemanticClassifier


class FakeRuntime:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return self.response


class DecisionAdapterTests(unittest.TestCase):
    def test_semantic_classifier_is_exposed_from_decision_module(self):
        self.assertIs(SemanticClassifier, DecisionSemanticClassifier)
        self.assertIs(SemanticClassifier, LegacySemanticClassifier)

    def test_score_evaluator_builds_score_request_and_returns_score_result(self):
        runtime = FakeRuntime(
            {
                "answers": {
                    "risk_score": {
                        "type": "score",
                        "score": 3.5,
                        "confidence": 0.88,
                        "legend": {"0": "low", "5": "high"},
                        "probabilities": {"3": 0.12, "4": 0.88},
                    }
                }
            }
        )
        evaluator = ScoreEvaluator(
            name="risk_score",
            criteria=["0 = low", "5 = high"],
            runtime=runtime,
            instructions="Score the risk from 0 to 5.",
        )

        result = evaluator.evaluate({"description": "Repeated payment failures"})

        self.assertIsInstance(result, ScoreResult)
        self.assertEqual(result.score, 3.5)
        self.assertEqual(result.confidence, 0.88)
        self.assertEqual(runtime.requests[0].state, {"description": "Repeated payment failures"})
        self.assertEqual(runtime.requests[0].questions["risk_score"]["type"], "score")
        self.assertEqual(
            runtime.requests[0].questions["risk_score"]["criteria"],
            ["0 = low", "5 = high"],
        )

    def test_noul_evaluator_returns_probability_and_boolean_view(self):
        runtime = FakeRuntime(
            {"answers": {"needs_review": {"type": "noul", "noul": 0.82}}}
        )
        evaluator = NoulEvaluator(
            name="needs_review",
            criteria="Determine whether this case requires human review.",
            runtime=runtime,
        )

        result = evaluator.evaluate({"description": "Suspicious transaction"})

        self.assertIsInstance(result, NoulResult)
        self.assertEqual(result.probability, 0.82)
        self.assertTrue(result.is_true())
        self.assertEqual(runtime.requests[0].questions["needs_review"]["type"], "noul")

    def test_noul_result_can_use_a_custom_threshold(self):
        result = NoulResult(probability=0.62)

        self.assertFalse(result.is_true(threshold=0.7))
        self.assertEqual(result.to_dict(), {"probability": 0.62})

    def test_score_evaluator_can_be_created_from_a_score_definition(self):
        definition = DecisionDefinition.from_mapping(
            {
                "version": 1,
                "kind": "score",
                "name": "risk_score",
                "input": {
                    "type": "text",
                    "field": "description",
                    "instructions": "Score the risk from 0 to 5.",
                },
                "criteria": ["0 = low", "5 = high"],
            }
        )
        runtime = FakeRuntime(
            {"answers": {"risk_score": {"score": 4, "confidence": 0.9}}}
        )

        result = ScoreEvaluator.from_definition(definition, runtime=runtime).evaluate(
            "Repeated payment failures"
        )

        self.assertEqual(result.score, 4.0)
        self.assertEqual(runtime.requests[0].state, {"description": "Repeated payment failures"})

    def test_noul_evaluator_can_be_created_from_a_noul_definition(self):
        definition = DecisionDefinition.from_mapping(
            {
                "version": 1,
                "kind": "noul",
                "name": "needs_review",
                "input": {"type": "text", "field": "description"},
                "criteria": {
                    "true": "The case requires human review.",
                    "false": "The case does not require human review.",
                },
            }
        )
        runtime = FakeRuntime({"answers": {"needs_review": {"noul": 0.8}}})

        result = NoulEvaluator.from_definition(definition, runtime=runtime).evaluate(
            "Suspicious transaction"
        )

        self.assertEqual(result.probability, 0.8)
        self.assertEqual(runtime.requests[0].state, {"description": "Suspicious transaction"})


if __name__ == "__main__":
    unittest.main()
