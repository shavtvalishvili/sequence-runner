import asyncio
import json
import traceback
import nest_asyncio
from http import HTTPStatus
from dotenv import load_dotenv
from src.data.secrets_manager import SecretsManager
from src.sequence.sequence_runner import SequenceRunner
from langsmith import Client as LangSmithClient


async def async_lambda_handler(event, _context):
    load_dotenv()
    secretsManager = SecretsManager()
    secretsManager.update_env_with_secrets()
    payload = json.loads(event.get("body", "{}"))

    sequence_id = payload["sequence_id"]
    client_id = payload["client_id"]
    product_id = payload["product_id"]
    initial_state = payload.get("initial_state")

    langsmith_client = LangSmithClient()
    try:
        sequence_runner = SequenceRunner(sequence_id, client_id, product_id, initial_state)
        await sequence_runner.load_configurations()
        final_graph_state = await sequence_runner.run_sequence_async()
        response = {"statusCode": HTTPStatus.OK, "body": json.dumps(final_graph_state)}
    except Exception as e:
        print(traceback.format_exc())
        response = {"statusCode": HTTPStatus.INTERNAL_SERVER_ERROR, "body": json.dumps({"message": str(e)})}
    langsmith_client.flush()

    return response


def lambda_handler(event, _context):
    nest_asyncio.apply()

    return asyncio.run(async_lambda_handler(event, _context))
