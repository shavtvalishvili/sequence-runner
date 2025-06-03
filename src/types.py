from http import HTTPStatus
from typing import Any, Dict, NotRequired, TypedDict


class SequenceRunnerPayload(TypedDict):
    sequence_id: str
    client_id: str
    product_id: str
    initial_state: NotRequired[Dict[str, Any]]


class SequenceRunnerResponse(TypedDict):
    statusCode: HTTPStatus
    body: str
