import unittest

from typesafe_jev import DecisionRequest, JevResponse, JevRuntime, JevRuntimeError


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def system_one(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeSdkAnswer:
    def __init__(self, value):
        self.value = value

    def model_dump(self):
        return self.value


class FakeSdkResponse:
    def __init__(self):
        self.answers = {
            "ticket_classifier": FakeSdkAnswer(
                {"type": "choice", "choice": "incident", "confidence": 0.9}
            )
        }
        self.usage = {"input_tokens": 10}
        self.model = "jev-test"


class JevRuntimeTests(unittest.TestCase):
    def test_normalizes_sdk_response_and_passes_request(self):
        client = FakeClient([FakeSdkResponse()])
        runtime = JevRuntime(client=client, model="jev-test", timeout=3)
        request = DecisionRequest(
            state={"description": "failure"},
            questions={"ticket_classifier": {"type": "choice"}},
        )

        response = runtime.execute(request)

        self.assertIsInstance(response, JevResponse)
        self.assertEqual(response.answers["ticket_classifier"]["choice"], "incident")
        self.assertEqual(client.calls[0]["timeout"], 3)

    def test_retries_then_succeeds_and_cache_avoids_second_call(self):
        client = FakeClient([TimeoutError("temporary"), FakeSdkResponse()])
        runtime = JevRuntime(client=client, model="jev-test", retry=1, cache=True)
        request = DecisionRequest(state="failure", questions={"q": {"type": "choice"}})

        first = runtime.execute(request)
        second = runtime.execute(request)

        self.assertEqual(len(client.calls), 2)
        self.assertEqual(first.answers, second.answers)

    def test_converts_api_failure_to_unified_runtime_error(self):
        client = FakeClient([ConnectionError("offline")])
        runtime = JevRuntime(client=client)

        with self.assertRaises(JevRuntimeError) as context:
            runtime.execute(DecisionRequest(state="failure", questions={"q": {}}))

        self.assertEqual(context.exception.code, "API_ERROR")


if __name__ == "__main__":
    unittest.main()
