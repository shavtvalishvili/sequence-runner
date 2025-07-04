import json

from src.app import lambda_handler

if __name__ == "__main__":
    with open("tests/fixtures/test_event.json") as f:
        event = {"body": json.dumps(json.load(f))}

    result = lambda_handler(event, None)
    print(json.dumps(result, indent=2))
