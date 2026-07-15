"""
main.py  –  FastAPI backend for ork2step

Endpoints
---------
POST /upload          Upload a .ork file → returns parse summary + any missing params
POST /generate        Submit missing params + session id → returns STEP file
GET  /health          Liveness check
"""

from __future__ import annotations

import faulthandler
import sys

# Ask Python to dump a stack trace to stderr if the process receives a
# fatal signal (e.g. SIGSEGV from the native OCCT/CAD kernel). This can't
# "fix" a native crash, but it turns a silent "python quit unexpectedly"
# into a printed traceback showing which Python line was running when it
# happened — that's the fastest way to find the actual offending geometry.
faulthandler.enable(file=sys.stderr, all_threads=True)

import os
import uuid
import logging
import tempfile
from typing import Any

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel

from ork_parser import OrkParser, OrkParseError, MissingParam, Rocket, summarise
from cad_builder import CadBuilder, CadBuildError

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("ork2step")

# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------
app = FastAPI(
    title="ork2step",
    description="Convert OpenRocket .ork files to STEP for Fusion 360",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory session store  (use Redis / DB in production)
# ---------------------------------------------------------------------------
# sessions[session_id] = {
#     "rocket": Rocket,
#     "missing": [MissingParam],
# }
_sessions: dict[str, dict] = {}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class MissingParamInfo(BaseModel):
    component_name: str
    param_name: str
    description: str
    unit: str
    default: float


class UploadResponse(BaseModel):
    session_id: str
    rocket_name: str
    summary: str
    missing_params: list[MissingParamInfo]
    component_count: int


class GenerateRequest(BaseModel):
    session_id: str
    # Map of "component_name::param_name" → value (in the unit shown in MissingParamInfo)
    param_overrides: dict[str, float] = {}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload", response_model=UploadResponse)
async def upload_ork(file: UploadFile = File(...)):
    """
    Accept a .ork file, parse it, and return structure info + any missing params.
    """
    # ---- basic validation -------------------------------------------------
    filename = file.filename or ""
    if not filename.lower().endswith(".ork"):
        raise HTTPException(
            status_code=400,
            detail="Only .ork files (OpenRocket) are accepted.",
        )

    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {MAX_FILE_SIZE // 1024 // 1024} MB).",
        )
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # ---- parse ------------------------------------------------------------
    parser = OrkParser()
    try:
        rocket, missing = parser.parse_bytes(raw)
    except OrkParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # ---- store session ----------------------------------------------------
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {"rocket": rocket, "missing": missing}

    # ---- count components ------------------------------------------------
    count = sum(1 for _ in _all_components(rocket))

    return UploadResponse(
        session_id=session_id,
        rocket_name=rocket.name,
        summary=summarise(rocket),
        missing_params=[
            MissingParamInfo(
                component_name=m.component_name,
                param_name=m.param_name,
                description=m.description,
                unit=m.unit,
                default=m.default,
            )
            for m in missing
        ],
        component_count=count,
    )


@app.post("/generate")
async def generate_step(req: GenerateRequest, background_tasks: BackgroundTasks):
    """
    Apply any user-supplied missing parameters and build a STEP file.
    Returns the binary STEP data directly (Content-Disposition: attachment).
    """
    session = _sessions.get(req.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired.  Please re-upload your file.",
        )

    rocket: Rocket = session["rocket"]
    missing: list[MissingParam] = session["missing"]

    # ---- apply overrides --------------------------------------------------
    _apply_overrides(rocket, missing, req.param_overrides)

    # ---- build STEP -------------------------------------------------------
    log.info("Starting CAD build for rocket '%s'...", rocket.name)
    try:
        builder = CadBuilder()
        step_bytes = builder.build_step(rocket)
    except CadBuildError as exc:
        log.error("CAD build failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"CAD generation failed: {exc}",
        )
    except Exception as exc:
        log.exception("Unexpected error during CAD build")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during model generation: {exc}",
        )
    log.info("CAD build finished (%d bytes)", len(step_bytes))

    # Clean up session after successful generation
    background_tasks.add_task(_sessions.pop, req.session_id, None)

    safe_name = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in rocket.name
    )
    filename = f"{safe_name}.step"

    return Response(
        content=step_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_overrides(
    rocket: Rocket,
    missing: list[MissingParam],
    overrides: dict[str, float],
) -> None:
    """
    Apply user-supplied values back onto the rocket's components.
    Key format:  "<component_name>::<param_name>"
    Values are in the unit declared by MissingParam.unit (mm → convert to metres).
    """
    from ork_parser import _walk_list

    # Build a lookup of component name → component object
    comp_by_name: dict[str, Any] = {}
    for stage in rocket.stages:
        for comp in _walk_list(stage):
            comp_by_name[comp.name] = comp

    for key, value in overrides.items():
        if "::" not in key:
            continue
        comp_name, param_name = key.split("::", 1)
        comp = comp_by_name.get(comp_name)
        if comp is None:
            continue

        # Find the declared unit for this param
        unit = next(
            (m.unit for m in missing if m.component_name == comp_name and m.param_name == param_name),
            "mm",
        )
        # Convert to metres if needed
        value_m = value / 1000.0 if unit == "mm" else value

        if hasattr(comp, param_name):
            setattr(comp, param_name, value_m)


def _all_components(rocket: Rocket):
    from ork_parser import _walk_list
    for stage in rocket.stages:
        yield from _walk_list(stage)


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
