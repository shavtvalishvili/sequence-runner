import asyncio
import json
from http import HTTPStatus

from dotenv import load_dotenv

from src.data.secrets_manager import SecretsManager
from src.sequence.sequence_runner import SequenceRunner
import traceback
import nest_asyncio


async def async_lambda_handler(event, _context):
    load_dotenv()
    secretsManager = SecretsManager()
    secretsManager.update_env_with_secrets()

    sequence_id = event["sequence_id"]
    client_id = event["client_id"]
    product_id = event["product_id"]
    initial_state = event.get("initial_state")

    try:
        sequence_runner = SequenceRunner(sequence_id, client_id, product_id, initial_state)
        await sequence_runner.load_configurations()
        final_graph_state = await sequence_runner.run_sequence_async()
        return {"statusCode": HTTPStatus.OK, "body": json.dumps(final_graph_state)}
    except Exception as e:
        print(traceback.format_exc())
        return {"statusCode": HTTPStatus.INTERNAL_SERVER_ERROR, "body": json.dumps({"message": str(e)})}


def lambda_handler(event, _context):
    nest_asyncio.apply()

    return asyncio.run(async_lambda_handler(event, _context))
