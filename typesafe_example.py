from typesafe_sdk import Score

from typesafe_client import create_client, load_config


config = load_config()

with create_client(config) as client:
    result = client.system_one(
        state="页面加载要 8 秒，用户一直在投诉。",
        model=config.model,
        questions={
            "urgency": Score(
                instructions="How urgent is this?",
                criteria=["Can wait", "This week", "Today"],
            )
        },
    )

print(result.scores["urgency"].score, result.scores["urgency"].confidence)
