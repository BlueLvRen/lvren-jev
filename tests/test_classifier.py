import unittest

from typesafe_jev import (
    CategoryDefinition,
    ClassificationResult,
    DecisionDefinition,
    DecisionPolicy,
    FallbackPolicy,
    SemanticClassifier,
)


class FakeRuntime:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return self.response


def make_definition(threshold=0.65):
    return DecisionDefinition(
        name="ticket_classifier",
        categories={
            "incident": CategoryDefinition("incident", "Incident", "Production failure"),
            "feature": CategoryDefinition("feature", "Feature", "New capability"),
        },
        policy=DecisionPolicy(
            threshold=threshold,
            fallback=FallbackPolicy("pending", "Pending review"),
        ),
    )


class SemanticClassifierTests(unittest.TestCase):
    def test_classifies_choice_and_builds_generic_request(self):
        runtime = FakeRuntime(
            {
                "answers": {
                    "ticket_classifier": {
                        "type": "choice",
                        "choice": "incident",
                        "confidence": 0.91,
                        "probabilities": {"incident": 0.91, "feature": 0.09},
                    }
                }
            }
        )
        classifier = SemanticClassifier.from_definition(make_definition(), runtime=runtime)

        result = classifier.classify("Production Redis connection failure")

        self.assertIsInstance(result, ClassificationResult)
        self.assertEqual(result.value, "incident")
        self.assertEqual(result.label, "Incident")
        self.assertFalse(result.fallback)
        self.assertEqual(runtime.requests[0].state, {"description": "Production Redis connection failure"})
        self.assertEqual(runtime.requests[0].questions["ticket_classifier"]["type"], "choice")

    def test_returns_fallback_when_confidence_is_below_threshold(self):
        runtime = FakeRuntime(
            {
                "answers": {
                    "ticket_classifier": {
                        "choice": "feature",
                        "confidence": 0.48,
                        "probabilities": {"incident": 0.48, "feature": 0.52},
                    }
                }
            }
        )
        classifier = SemanticClassifier.from_definition(make_definition(), runtime=runtime)

        result = classifier.classify("Something ambiguous")

        self.assertEqual(result.value, "pending")
        self.assertEqual(result.label, "Pending review")
        self.assertEqual(result.confidence, 0.48)
        self.assertTrue(result.fallback)

    def test_rejects_unknown_selected_category(self):
        runtime = FakeRuntime(
            {"answers": {"ticket_classifier": {"choice": "missing", "confidence": 0.9}}}
        )
        classifier = SemanticClassifier.from_definition(make_definition(), runtime=runtime)

        with self.assertRaisesRegex(ValueError, "unknown category"):
            classifier.classify("bad response")


if __name__ == "__main__":
    unittest.main()
