"""Run this model in Python

> pip install openai
"""
from openai import OpenAI

client = OpenAI(
    base_url = "http://localhost:5272/v1/",
    api_key = "unused", # required for the API but not used
)

response = client.chat.completions.create(
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "what kind of llm are you? can you go agentic stuff?",
                },
            ],
        },
    ],
    model = "mistral-7b-v02-int4-cpu",
    max_tokens = 256,
    frequency_penalty = 1,
)

print(response.choices[0].message.content)