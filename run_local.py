import asyncio
import json
from app import lambda_handler

if __name__ == "__main__":
    with open("test_event.json") as f:
        event = json.load(f)

    result = asyncio.run(lambda_handler(event, None))
    print(json.dumps(result, indent=2))
