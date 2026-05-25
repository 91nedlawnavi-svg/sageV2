import boto3
import json

MODEL_ID = "us.anthropic.claude-opus-4-6-v1"

client = boto3.client(
    service_name="bedrock-runtime",
    region_name="us-east-1"
)

body = {
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 1000,
    "messages": [
        {
            "role": "user",
            "content": "Explain the primary long-term failure modes of recursive reflective cognition systems."
        }
    ]
}

response = client.invoke_model(
    modelId=MODEL_ID,
    body=json.dumps(body),
)

data = json.loads(response["body"].read())

print(data["content"][0]["text"])
