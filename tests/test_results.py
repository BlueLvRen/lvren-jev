import unittest

from typesafe_jev import ClassificationResult


class ClassificationResultTests(unittest.TestCase):
    def test_result_is_serializable_and_keeps_program_value(self):
        result = ClassificationResult(
            value="incident",
            label="Incident",
            confidence=0.91,
            probabilities={"incident": 0.91, "feature": 0.09},
        )

        self.assertEqual(result.to_dict()["value"], "incident")
        self.assertEqual(result.to_dict()["label"], "Incident")
        self.assertFalse(result.to_dict()["fallback"])

    def test_rejects_confidence_outside_probability_range(self):
        with self.assertRaises(ValueError):
            ClassificationResult(value="a", label="A", confidence=1.1)


if __name__ == "__main__":
    unittest.main()
