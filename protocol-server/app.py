# app.py
from typing import List, Dict, Any, Optional
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field
import time

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field, ConfigDict, RootModel

from pathing import FOAM_RUN, FOAM_BASHRC
import utils as util
from file_generator import FileGenerator
from turbine_model import TurbineModel
import errno
import selectors
import json
from typing import Optional, Dict, Any, List

app = FastAPI()


# In-memory session registry:
class State(str, Enum):
    initializing = "initializing"
    ready = "ready"
    stepping = "stepping"
    terminating = "terminating"
    error = "error"


@dataclass
class Session:
    case_dir: str
    proc: subprocess.Popen | None = None
    state: State = State.initializing
    op_seq: int = 0
    last_error: str | None = None
    progress: float = 0.0
    t: float = 0.0
    message: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    step_fd: Optional[int] = None
    last_telemetry: Optional[Dict[str, Any]] = None  # <-- ADDED: Stores the STEPPED JSON with loads


SESS: Dict[str, Session] = {}


# ---------------------------
# Pydantic models (Simplified for brevity)
# ---------------------------


class Meta(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_name: str = Field(alias="schema")
    num_blades: int
    num_nodes_per_blade: int


class Hub(BaseModel):  # Minimal structure for demonstration
    pos: List[float]
    ori: List[float]
    vel: List[float]
    acc: List[float]


class Root(BaseModel):  # Minimal structure for demonstration
    pos: List[List[float]]
    ori: List[List[float]]
    vel: List[List[float]]
    acc: List[List[float]]


class Mesh(BaseModel):  # Minimal structure for demonstration
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
    template_dir: Optional[str] = None


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


class RunOptions:
    def __init__(self):
        # ... (unchanged) ...
        self.case_name = "test_case"
        self.case_class = "axialFlowTurbineAL"
        self.num_revolutions = 1
        self.time_step = 5
        self.model_tower = False
        self.model_hub = False
        self.tip_speed_ratio = 8
        self.wind_speed = 12.8
        self.twist_offset = 0.0
        self.tilt_angle = -6.0


# ---------------------------
# Helpers
# ---------------------------


def _ack(sid: str, sess: Session) -> dict:
    return {"status": "accepted", "session_id": sid, "op_seq": sess.op_seq}


def _apply_op(sess: Session):
    sess.op_seq += 1


def open_step_writer(case_dir: Path) -> int:
    path = case_dir / "step.pipe"
    return os.open(str(path), os.O_WRONLY)


def write_step_to_fd(fd: int, dt: float):
    os.write(fd, f"{dt}\n".encode("ascii"))


def _bootstrap_session(sid: str, payload: InitializeIn, background_tasks: BackgroundTasks):
    sess = SESS[sid]
    try:
        case_dir = Path(sess.case_dir)

        # 1. Start solver & reader
        proc = start_allrun(case_dir)
        sess.proc = proc
        background_tasks.add_task(_perf_reader_task, sid)

        # 2. Open persistent step writer (Blocks until solver is ready to read)
        sess.step_fd = open_step_writer(case_dir)

        # 3. UNBLOCK THE SOLVER'S INITIAL BLOCK and allow it to send READY
        os.write(sess.step_fd, "CONT\n".encode("ascii"))

        sess.message = "Solver launched. Waiting for READY signal..."
        _apply_op(sess)

    except Exception as e:
        sess.state = State.error
        sess.last_error = str(e)
        _apply_op(sess)


# ---------------------------
# HTTP endpoints
# ---------------------------


@app.post("/initialize", status_code=202)
def initialize(payload: InitializeIn, background_tasks: BackgroundTasks):
    sid = str(uuid.uuid4())
    util.make_directory_in_foam_run(sid)
    util.clear_case_directory(sid)
    util.copy_axial_turbine_case(sid)

    model = TurbineModel(name="IEA_15MW_AB_OF")
    model.read_from_yaml()
    run_opts = RunOptions()
    FileGenerator(model, run_opts).generate_files(FOAM_RUN / sid)

    mkfifos(FOAM_RUN / sid)
    SESS[sid] = Session(case_dir=str(FOAM_RUN / sid), state=State.initializing, op_seq=0)

    background_tasks.add_task(_bootstrap_session, sid, payload, background_tasks)

    return _ack(sid, SESS[sid])


@app.get("/status/{sid}")
def status(sid: str):
    sess = SESS.get(sid)
    if not sess:
        raise HTTPException(404, "unknown session")
    return {
        "state": sess.state,
        "op_seq": sess.op_seq,
        "progress": sess.progress,
        "message": sess.message,
        "t": sess.t,
        "last_error": sess.last_error,
        "last_outputs": sess.last_telemetry,  # <-- FINAL DATA POINT FOR FMU
    }


@app.post("/step", status_code=202)
def step(payload: StepIn, background_tasks: BackgroundTasks):
    sid = payload.session_id
    sess = SESS.get(sid)
    if not sess:
        raise HTTPException(404, "invalid session_id")
    if sess.state != State.ready:
        raise HTTPException(409, f"busy: state={sess.state}")

    sess.state = State.stepping
    _apply_op(sess)
    current_op = sess.op_seq

    background_tasks.add_task(_do_step, sid, payload, current_op)
    return _ack(sid, sess)


def _do_step(sid: str, payload: StepIn, op_seq: int):
    sess = SESS.get(sid)
    if not sess or sess.op_seq != op_seq:
        return
    try:
        if sess.step_fd is None:
            raise RuntimeError("Step FD was not initialized.")

        write_step_to_fd(sess.step_fd, payload.dt)

        sess.t = payload.t + payload.dt
        sess.message = f"Advanced dt={payload.dt}. Waiting for STEPPED signal..."

    except Exception as e:
        sess.state = State.error
        sess.last_error = str(e)
        _apply_op(sess)


@app.post("/terminate", status_code=202)
def terminate(payload: Dict[str, str], background_tasks: BackgroundTasks):
    sid = payload.get("session_id")
    if not sid:
        raise HTTPException(400, "session_id required")

    sess = SESS.get(sid)
    if not sess:
        return {"status": "accepted"}

    if sess.state == State.terminating:
        return _ack(sid, sess)

    sess.state = State.terminating
    _apply_op(sess)
    current_op = sess.op_seq
    background_tasks.add_task(_do_terminate, sid, current_op)
    return _ack(sid, sess)


def _do_terminate(sid: str, op_seq: int):
    sess = SESS.get(sid)
    if not sess or sess.op_seq != op_seq:
        return
    try:
        if sess.step_fd is not None:
            os.write(sess.step_fd, "STOP\n".encode("ascii"))
            os.close(sess.step_fd)
            sess.step_fd = None

        if sess.proc is not None:
            try:
                sess.proc.wait(timeout=10)
            except Exception:
                sess.proc.kill()
        shutil.rmtree(sess.case_dir, ignore_errors=True)
    finally:
        SESS.pop(sid, None)


# ---------------------------
# Background Tasks (Perf Reader)
# ---------------------------


def _open_perf_reader(case_dir: Path):
    """Open perf.pipe for non-blocking reads."""
    perf_path = case_dir / "perf.pipe"
    fd = os.open(perf_path, os.O_RDONLY | os.O_NONBLOCK)
    return os.fdopen(fd, "r", buffering=1)


def _perf_reader_task(sid: str):
    """Asynchronously monitors perf.pipe for solver signals (READY, STEPPED)."""
    sess = SESS.get(sid)
    if not sess:
        return

    case_dir = Path(sess.case_dir)
    try:
        fh = _open_perf_reader(case_dir)
    except Exception:
        sess = SESS.get(sid)
        if sess:
            sess.state = State.error
            sess.last_error = "Could not open perf.pipe for reading."
        return

    sel = selectors.DefaultSelector()
    sel.register(fh, selectors.EVENT_READ)

    try:
        while True:
            if sid not in SESS:
                break
            events = sel.select(timeout=1.0)
            if not events:
                continue

            line = fh.readline()
            if not line:
                sess = SESS.get(sid)
                if sess:
                    sess.state = State.error
                    sess.last_error = "Solver process closed perf.pipe."
                    _apply_op(sess)
                break

            s = line.strip()
            try:
                msg = json.loads(s)
            except Exception:
                msg = {"type": "TEXT", "raw": s}

            sess = SESS.get(sid)
            if not sess:
                break

            typ = msg.get("type", "").upper()
            if typ == "READY":
                sess.state = State.ready
                sess.message = "Solver signaled READY."
                sess.progress = 1.0
                _apply_op(sess)
            elif typ == "STEPPED":
                if "time" in msg:
                    try:
                        sess.t = float(msg["time"])
                    except Exception:
                        pass

                sess.last_telemetry = msg  # <--- STORE THE FULL JSON MESSAGE (contains meshFrcMom)

                sess.state = State.ready
                sess.message = f"Step complete. t={sess.t:.3f}"
                _apply_op(sess)
            else:
                sess.message = f"Solver log: {s[:50]}..."

    finally:
        try:
            sel.unregister(fh)
        except Exception:
            pass
        try:
            fh.close()
        except Exception:
            pass


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
