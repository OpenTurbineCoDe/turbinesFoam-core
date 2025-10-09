# app.py
from typing import List, Dict, Any, Optional
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field, ConfigDict, RootModel

from pathing import FOAM_RUN, FOAM_BASHRC
import utils as util
from file_generator import FileGenerator
from turbine_model import TurbineModel

app = FastAPI()

# In-memory session registry:
#   key: session_id (str)
#   val: {"case_dir": str, "proc": Popen | None, ...}
SESS: Dict[str, Dict[str, Any]] = {}


# ---------------------------
# Pydantic models (v2 style)
# ---------------------------


class Meta(BaseModel):
    """
    Example metadata passed by the client.

    - model_config: enables population by field *alias* (so payload key "schema"
      loads into our 'schema_name' field).
    - Field(alias="schema"): tells Pydantic that the incoming JSON key is 'schema',
      but we expose the attribute as 'schema_name' in Python.
    """

    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(alias="schema")  # incoming key "schema" -> schema_name
    num_blades: int
    num_nodes_per_blade: int


# RootModel is a thin wrapper to say "this model IS this type".
# Useful when you want a type alias that still validates as a model.
# Example: payload might contain arrays of fixed meaning.
class R6(RootModel[List[float]]):
    """Represents a flat list[6] of floats (e.g., [x,y,z,rx,ry,rz])."""

    pass


class R9(RootModel[List[float]]):
    """Represents a flat list[9] of floats (e.g., orientation matrix)."""

    pass


# The following nested structures model the kinematics blocks coming from the FMU.
# Each field is a list-of-floats; you can replace these with R6/R9 for stricter shapes.


class Hub(BaseModel):
    """Rigid-body hub/nacelle state (pos/orientation/vel/acc)."""

    pos: List[float]
    ori: List[float]
    vel: List[float]
    acc: List[float]


class Root(BaseModel):
    """Per-blade root states (list over blades)."""

    pos: List[List[float]]
    ori: List[List[float]]
    vel: List[List[float]]
    acc: List[List[float]]


class Mesh(BaseModel):
    """Per-blade, per-node actuator-line states."""

    pos: List[List[float]]
    ori: List[List[float]]
    vel: List[List[float]]
    acc: List[List[float]]


class InitialState(BaseModel):
    """Initial CFD-side state snapshot at t0."""

    t0: float
    hub: Hub
    nacelle: Hub
    root: Root
    mesh: Mesh


class InitializeIn(BaseModel):
    """
    Top-level /initialize payload.

    - meta: metadata/config that may control sizing or mapping
    - constants: scalar constants (e.g., wind speed, rho, TSR setpoints, etc.)
    - initial_state: full initial kinematic state to seed the simulation
    """

    meta: Meta
    constants: Dict[str, float]
    initial_state: InitialState
    # Optional: template dir or other hints
    template_dir: Optional[str] = None


class StepInputs(BaseModel):
    """Inputs at each step (same structure as parts of InitialState, plus meta)."""

    hub: Hub
    nacelle: Hub
    root: Root
    mesh: Mesh
    meta: Meta


class StepIn(BaseModel):
    """
    /step payload.

    - session_id: which running case to apply inputs to
    - t, dt: wall/sim time bookkeeping
    - inputs: the kinematic prescription for this step
    """

    session_id: str
    t: float
    dt: float
    inputs: StepInputs


# Simple holder for run configuration used by your FileGenerator
class RunOptions:
    def __init__(self):
        self.case_name = "test_case"
        self.case_class = "axialFlowTurbineAL"
        self.num_revolutions = 1
        self.time_step = 5  # degrees per time step (used by your generator)
        self.model_tower = False
        self.model_hub = False
        self.tip_speed_ratio = 8
        self.wind_speed = 12.8  # m/s
        self.twist_offset = 0.0
        self.tilt_angle = -6.0  # degrees


# ---------------------------
# HTTP endpoints
# ---------------------------


@app.post("/initialize", status_code=202)
def initialize(payload: InitializeIn, background_tasks: BackgroundTasks):
    """
    Prepares a fresh per-session case directory and (optionally) spawns the solver.

    Returns: { "status": "ok", "session_id": "<uuid>" }
    """
    print("Received /initialize payload")
    sid = str(uuid.uuid4())

    # Create/clean a case directory under FOAM_RUN/<sid>
    util.make_directory_in_foam_run(sid)
    util.clear_case_directory(sid)
    util.copy_axial_turbine_case(sid)  # copies your base case template to FOAM_RUN/<sid>

    # Generate case-specific files
    model = TurbineModel(name="IEA_15MW_AB_OF")  # choose based on payload if needed
    model.read_from_yaml()  # loads from models YAML
    run_opts = RunOptions()
    FileGenerator(model, run_opts).generate_files(FOAM_RUN / sid)

    # Create the step FIFO
    case_dir = FOAM_RUN / sid
    mkfifos(case_dir)
    SESS[sid] = {"case_dir": str(case_dir), "proc": None, "status": "initializing"}

    background_tasks.add_task(_boostrap_session, sid, payload)

    return {"status": "accepted", "session_id": sid}


def _boostrap_session(sid: str, payload: InitializeIn):
    """Background task to bootstrap a new session.

    Args:
        sid (str): Session ID
        payload (InitializeIn): Initialization payload

    Returns:
        _type_: _description_
    """
    try:
        print(f"Bootstrapping session {sid} in background task")

        # 5) Any other “one-shot” initialization
        util.initialize_run(sid)

        # 6) Start the Allrun script to launch the solver
        case_dir = Path(SESS[sid]["case_dir"])
        proc = start_allrun(case_dir)
        SESS[sid]["proc"] = proc
        SESS[sid]["status"] = "ready"
    except Exception as e:
        print(f"Error bootstrapping session {sid}: {e}")
        SESS[sid]["status"] = f"error: {e}"

    return {"status": "ok", "session_id": sid}


@app.get("/status/{sid}")
def status(sid: str):
    s = SESS.get(sid)
    if not s:
        raise HTTPException(404, "unknown session")
    return {"status": s.get("status")}


@app.post("/step")
def step(payload: StepIn):
    """
    Pushes one time step:
      - writes dt to the step FIFO to let the solver advance a single CFD step
      - (later) can stream kinematic inputs to your turbinesFoam API before the step
    """
    print("Received /step payload")
    sid = payload.session_id
    sess = SESS.get(sid)
    if not sess:
        raise HTTPException(status_code=404, detail="invalid session_id")

    print(f"Stepping session {sid} at t={payload.t} by dt={payload.dt}")
    case_dir = Path(sess["case_dir"])

    # TODO: map payload.inputs.* into your turbinesFoam external kinematics API here
    # e.g., write a JSON command file or call a small Python<->C++ bridge

    print(f"Writing dt={payload.dt} to FIFO to advance one CFD step")
    # Minimal protocol-first: write dt to FIFO; solver advances one step
    write_step(case_dir, payload.dt)

    # Return some echo/telemetry if you have it (e.g., azimuth, forces)
    return {"status": "ok", "t": payload.t + payload.dt}


@app.post("/terminate")
def terminate(payload: Dict[str, str]):
    """
    Gracefully stop a running session:
      - ask solver to exit
      - reap the process
      - delete the case directory
    """
    sid = payload.get("session_id")
    if not sid:
        raise HTTPException(status_code=400, detail="session_id required")

    sess = SESS.pop(sid, None)
    if not sess:
        # idempotent: it's already gone
        return {"status": "ok"}

    case_dir = Path(sess["case_dir"])

    # 1) ask solver loop to stop
    send_stop(case_dir)

    # 2) reap process if present
    proc = sess.get("proc")
    if proc is not None:
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

    # 3) remove the session directory
    shutil.rmtree(case_dir, ignore_errors=True)
    return {"status": "ok"}


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------
# Local helpers
# ---------------------------


def mkfifos(case_dir: Path):
    step = case_dir / "step.pipe"
    if step.exists():
        step.unlink()
    os.mkfifo(step, 0o666)

    perf = case_dir / "perf.pipe"
    if perf.exists():
        perf.unlink()
    os.mkfifo(perf, 0o666)


def start_allrun(case_dir: Path) -> subprocess.Popen:
    """
    Launch the case's Allrun in its directory, with FOAM env and FIFO path.
    The solver should block on the FIFO after the first step, waiting for dt.
    """
    env = os.environ.copy()
    env["FOAM_STEP_FIFO"] = str(case_dir / "step.pipe")
    env["FOAM_PERF_FIFO"] = str(case_dir / "perf.pipe")
    return subprocess.Popen(
        ["bash", "-lc", f"source {FOAM_BASHRC} && chmod +x Allrun && ./Allrun"],
        cwd=str(case_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def write_step(case_dir: Path, dt: float):
    """Write a dt value to the FIFO to advance one CFD time step."""
    with open(case_dir / "step.pipe", "w", buffering=1) as f:
        f.write(f"{dt}\n")


def send_stop(case_dir: Path):
    """Signal the solver loop to stop via the FIFO."""
    try:
        with open(case_dir / "step.pipe", "w", buffering=1) as f:
            f.write("STOP\n")
    except Exception:
        pass
