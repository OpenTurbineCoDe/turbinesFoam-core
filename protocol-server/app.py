# app.py (additions)
from typing import List, Dict, Any
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from fastapi import FastAPI
from pydantic import BaseModel, Field, ConfigDict, RootModel
from file_generator import FileGenerator
from turbine_model import TurbineModel

app = FastAPI()
SESS: Dict[str, Dict[str, Any]] = {}
FOAM_BASHRC = "/usr/lib/openfoam/openfoam2406/etc/bashrc"


class Meta(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_name: str = Field(alias="schema")  # <<< renamed
    num_blades: int
    num_nodes_per_blade: int


# --- Root types (Pydantic v2) ---
class R6(RootModel[List[float]]):
    pass


class R9(RootModel[List[float]]):
    pass


# --------------------------------


class Hub(BaseModel):
    pos: List[float]
    ori: List[float]
    vel: List[float]
    acc: List[float]


class Root(BaseModel):
    pos: List[List[float]]
    ori: List[List[float]]
    vel: List[List[float]]
    acc: List[List[float]]


class Mesh(BaseModel):
    pos: List[List[float]]
    ori: List[List[float]]
    vel: List[List[float]]
    acc: List[List[float]]


class InitialState(BaseModel):
    t0: float
    hub: Hub
    nacelle: Hub
    root: Root
    mesh: Mesh


class InitializeIn(BaseModel):
    meta: Meta
    constants: Dict[str, float]
    initial_state: InitialState


class StepInputs(BaseModel):
    hub: Hub
    nacelle: Hub
    root: Root
    mesh: Mesh
    meta: Meta


class StepIn(BaseModel):
    session_id: str
    t: float
    dt: float
    inputs: StepInputs


FOAM_BASHRC = "/usr/lib/openfoam/openfoam2406/etc/bashrc"
SESS_ROOT = Path(os.environ.get("FOAM_SESS_ROOT", "/tmp/turbinesfoam/sessions"))
SESS_ROOT.mkdir(parents=True, exist_ok=True)


@app.post("/initialize")
def initialize(payload: InitializeIn):
    sid = str(uuid.uuid4())
    # case_dir = SESS_ROOT / sid
    # shutil.rmtree(case_dir, ignore_errors=True)
    # case_dir.mkdir(parents=True, exist_ok=True)

    # # 1) Generate case files (system/*, elementData, controlDict, etc.)
    # turbine = TurbineModel(name="IEA_15MW")  # or however you pick the model
    # turbine.read_from_yaml()  # if needed
    # run_options = ...  # build from payload/constants
    # FileGenerator(turbine, run_options).generate_files(case_dir)

    # # 2) Copy 0.org -> 0 (you need a 0.org in your template or generate one)
    # shutil.copytree(case_dir / "0.org", case_dir / "0", dirs_exist_ok=True)

    # # 3) Make FIFOs
    # mkfifos(case_dir)

    # # 4) Start Allrun (non-blocking)
    # proc = start_allrun(case_dir)

    # # store session
    # SESS[sid] = {"proc": proc, "case_dir": str(case_dir)}
    return {"status": "ok", "session_id": sid}


@app.post("/step")
def step(payload: StepIn):
    sid = payload["session_id"]
    sess = SESS.get(sid)
    if not sess:
        return {"status": "error", "message": "invalid session_id"}

    case_dir = Path(sess["case_dir"])
    with open(case_dir / "step.pipe", "w", buffering=1) as f:
        f.write(f"{payload['dt']}\n")  # one dt -> one CFD time step

    return {"status": "ok"}  # (add telemetry later if you wire a perf FIFO)


@app.post("/terminate")
def terminate(payload: Dict[str, str]):
    sid = payload.get("session_id")
    sess = SESS.pop(sid, None)
    if not sess:
        return {"status": "ok"}

    case_dir = Path(sess["case_dir"])
    # tell solver to exit its time loop
    try:
        with open(case_dir / "step.pipe", "w", buffering=1) as f:
            f.write("STOP\n")
    except Exception:
        pass

    # wait a moment and then nuke the session dir
    try:
        sess["proc"].wait(timeout=10)
    except Exception:
        sess["proc"].kill()
    shutil.rmtree(case_dir, ignore_errors=True)
    return {"status": "ok"}


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


# --- helpers (drop-in for app.py) ---


def mkfifos(case_dir: Path):
    step = case_dir / "step.pipe"
    if step.exists():
        step.unlink()
    os.mkfifo(step, 0o666)


def start_allrun(case_dir: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["FOAM_STEP_FIFO"] = str(case_dir / "step.pipe")
    # start Allrun in the case dir; it will block on step.pipe after first step
    return subprocess.Popen(
        ["bash", "-lc", f"source {FOAM_BASHRC} && chmod +x Allrun && ./Allrun"],
        cwd=str(case_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def write_step(case_dir: Path, dt: float):
    with open(case_dir / "step.pipe", "w", buffering=1) as f:
        f.write(f"{dt}\n")


def send_stop(case_dir: Path):
    try:
        with open(case_dir / "step.pipe", "w", buffering=1) as f:
            f.write("STOP\n")
    except Exception:
        pass
