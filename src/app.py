import asyncio
import json
import traceback
from http import HTTPStatus
from typing import Any

import nest_asyncio
from dotenv import load_dotenv
from langsmith import Client as LangSmithClient
from starlette.routing import Request

from src.data.secrets_manager import SecretsManager
from src.sequence.sequence_runner import SequenceRunner
from src.types import SequenceRunnerPayload, SequenceRunnerResponse


async def async_lambda_handler(event: Request, _context: Any) -> SequenceRunnerResponse:
    load_dotenv()
    secretsManager = SecretsManager()
    secretsManager.update_env_with_secrets()
    payload: SequenceRunnerPayload = json.loads(event.get("body"))

    sequence_id = payload["sequence_id"]
    client_id = payload["client_id"]
    product_id = payload["product_id"]
    initial_state = payload.get("initial_state")

    langsmith_client = LangSmithClient()
    try:
        sequence_runner = SequenceRunner(
            sequence_id, client_id, product_id, initial_state
        )
        await sequence_runner.load_configurations()
        final_graph_state = await sequence_runner.run_sequence_async()
        response: SequenceRunnerResponse = {
            "statusCode": HTTPStatus.OK,
            "body": json.dumps(final_graph_state),
        }
    except Exception as e:
        print(traceback.format_exc())
        response = {
            "statusCode": HTTPStatus.INTERNAL_SERVER_ERROR,
            "body": json.dumps({"message": str(e)}),
        }
    langsmith_client.flush()

    return response


def lambda_handler(event: Request, _context: Any) -> SequenceRunnerResponse:
    nest_asyncio.apply()

    return asyncio.run(async_lambda_handler(event, _context))
