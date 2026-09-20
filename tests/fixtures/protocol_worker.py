"""CPU-only wire stub; no coordinator state access and no model imports."""
import sys

from artcurator.worker_protocol import Request, Response

request = Request.model_validate_json(sys.stdin.read())
identities = request.input_ids
if len(sys.argv) > 1 and sys.argv[1] == "reorder":
    identities = tuple(reversed(identities))
response = Response(run_id=request.run_id, request_id=request.request_id,
                    handshake=request.handshake, input_ids=identities,
                    values=tuple((.25,) for _ in identities), provider="cuda:0")
print(response.model_dump_json())
