from sequence_runner import SequenceRunner
import traceback
import nest_asyncio


async def lambda_handler(event, _context):
    nest_asyncio.apply()
    sequence_id = event["sequence_id"]
    client_id = event["client_id"]
    product_id = event["product_id"]
    initial_state = event.get("initial_state")

    try:
        sequence_runner = SequenceRunner(sequence_id, client_id, product_id, initial_state)
        await sequence_runner.load_configurations()
        await sequence_runner.run_sequence_async()
        return {"status": "success"}
    except Exception as e:
        print(traceback.format_exc())
        return {"status": "error", "message": str(e)}
