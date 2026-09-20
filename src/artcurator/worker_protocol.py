"""Validated worker wire boundary; only the coordinator persists evidence."""
import json
import math
import subprocess
import time
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import db

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class Handshake(Wire):
    protocol: Literal["1.0"] = "1.0"
    build: Digest
    environment: Digest
    artifact: Digest
    preprocessing: Digest
    execution: Digest
    capabilities: tuple[str, ...]


class Request(Wire):
    run_id: str
    request_id: str
    handshake: Handshake
    input_ids: tuple[Digest, ...]
    deadline: float
    output_contract: Literal["outputs-v1"] = "outputs-v1"
    tensor_schema: Literal["rgb-u8-hwc-v1"] = "rgb-u8-hwc-v1"
    tensor_file: str = ""
    signal: str = "qrealign"


class Response(Wire):
    run_id: str
    request_id: str
    handshake: Handshake
    input_ids: tuple[Digest, ...]
    values: tuple[tuple[float, ...], ...]
    provider: Literal["cuda:0"]
    output_contract: Literal["outputs-v1"] = "outputs-v1"
    tensor_schema: Literal["rgb-u8-hwc-v1"] = "rgb-u8-hwc-v1"


class ProtocolError(RuntimeError):
    """Untrusted or stale evidence cannot be committed."""


def validate_response(request: Request, response: Response) -> None:
    """Exact association and finite/range checks precede every persistence operation."""
    if response.handshake != request.handshake:
        raise ProtocolError("handshake_mismatch")
    if (response.request_id != request.request_id or response.run_id != request.run_id
            or time.time() >= request.deadline):
        raise ProtocolError("stale_response")
    if (response.input_ids != request.input_ids or len(set(response.input_ids)) != len(response.input_ids)
            or len(response.values) != len(request.input_ids)):
        raise ProtocolError("input_identity_or_count_mismatch")
    if (response.output_contract != request.output_contract or response.tensor_schema != request.tensor_schema
            or response.provider != "cuda:0"):
        raise ProtocolError("output_contract_mismatch")
    width = 2 if request.signal == "hpsv3" else 1
    if any(len(row) != width or not all(math.isfinite(v) for v in row) for row in response.values):
        raise ProtocolError("invalid_output")
    if request.signal == "hpsv3" and any(row[1] < 0 for row in response.values):
        raise ProtocolError("invalid_sigma")
    if request.signal == "qrealign" and any(not 0 <= row[0] <= 1 for row in response.values):
        raise ProtocolError("invalid_range")


def exchange(out: Path, request: Request, command: list[str], *, transport=subprocess.run) -> Response | None:
    """Foreground, bounded exchange; timeout kills/reaps via subprocess.run, never scores zero."""
    try:
        remaining = request.deadline - time.time()
        if remaining <= 0:
            raise ProtocolError("expired_request")
        result = transport(command, input=request.model_dump_json(), text=True, capture_output=True,
                           timeout=min(240, remaining), check=True)
        response = Response.model_validate_json(result.stdout)
        validate_response(request, response)
        return response
    except subprocess.TimeoutExpired:
        reason = "timeout"
    except (subprocess.CalledProcessError, ValidationError, ProtocolError) as error:
        reason = str(error)
    db.meta(out, "worker_failure_" + request.request_id,
            json.dumps({"reason": reason, "status": "failed", "run_id": request.run_id,
                        "input_ids": request.input_ids, "signal": request.signal}))
    return None
