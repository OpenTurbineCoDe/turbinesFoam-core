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
import glob  # Used for file pattern matching

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field, ConfigDict, RootModel

# NOTE: You must ensure pandas is installed in your Docker environment!
import pandas as pd  # Used for efficient CSV reading
import numpy as np

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
    last_telemetry: Optional[Dict[str, Any]] = None  # Stores the STEPPED JSON + aggregated loads
    num_blades: int = 0
    num_nodes_per_blade: int = 0


SESS: Dict[str, Session] = {}


# ---------------------------
# Pydantic models
# ---------------------------


class Meta(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_name: str = Field(alias="schema")
    num_blades: int
    num_nodes_per_blade: int


class R6(RootModel[List[float]]):
    pass


class R9(RootModel[List[float]]):
    pass


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
# DATA AGGREGATION HELPER (Reads CSVs)
# ---------------------------


def aggregate_loads_from_csv(case_dir: Path, target_time: float) -> List[float]:
    """
    Reads all ActuatorLineElements CSV files for a specific time step, extracts
    Fx, Fy, Fz, and returns a flattened list of (Num_Nodes * 6) components
    [Fx, Fy, Fz, Mx=0, My=0, Mz=0].
    """
    # NOTE: Assuming the postProcessing directory is always '0'
    LOADS_DIR = case_dir / "postProcessing" / "actuatorLineElements" / "0"

    if not LOADS_DIR.exists():
        print(f"ERROR: Loads directory not found at {LOADS_DIR}")
        return []

    # Find all element CSVs (e.g., turbine.blade1.element*.csv)
    file_pattern = str(LOADS_DIR / "turbine.blade*.element*.csv")
    load_files = sorted(glob.glob(file_pattern))

    if not load_files:
        print(f"WARNING: No load CSV files found in {LOADS_DIR}")
        return []

    mesh_frc_mom = []
    TIME_COLUMN = "time"

    # Loop through each blade/element CSV file
    for file_path in load_files:
        try:
            df = pd.read_csv(file_path)

            # Find the row where the 'time' column is near the target_time
            time_match = df[
                df[TIME_COLUMN].astype(float).ge(target_time - 1e-6)
                & df[TIME_COLUMN].astype(float).le(target_time + 1e-6)
            ]

            if not time_match.empty:
                row = time_match.iloc[0]

                # Extracting the 3 force components (fx, fy, fz)
                fx = row["fx"]
                fy = row["fy"]
                fz = row["fz"]

                # Append the 6 components: 3 Forces + 3 Moments (placeholders)
                mesh_frc_mom.extend([float(fx), float(fy), float(fz), 0.0, 0.0, 0.0])  # M = 0.0 placeholders
            else:
                # Time step not found: return zeros for this element
                mesh_frc_mom.extend([0.0] * 6)

        except Exception as e:
            # Catch file read errors (e.g., missing columns, bad I/O)
            print(f"Error processing CSV {file_path}: {e}")
            mesh_frc_mom.extend([0.0] * 6)  # Maintain array size integrity

    return mesh_frc_mom


def aggregate_performance_from_csv(case_dir: Path, target_time: float) -> List[float]:
    """
    This reads the performance CSV files for a specific time step, and extracts
    the overall cp, ct, cq values for each blade, returning them as a flat list.
    """
    PERF_DIR = case_dir / "postProcessing" / "turbines" / "0"

    if not PERF_DIR.exists():
        print(f"ERROR: Performance directory not found at {PERF_DIR}")
        return []

    file_pattern = str(PERF_DIR / "turbine.csv")
    perf_files = sorted(glob.glob(file_pattern))

    if not perf_files:
        print(f"WARNING: No performance CSV files found in {PERF_DIR}")
        return []

    blade_performance = []
    TIME_COLUMN = "time"

    for file_path in perf_files:
        try:
            df = pd.read_csv(file_path)

            time_match = df[
                df[TIME_COLUMN].astype(float).ge(target_time - 1e-6)
                & df[TIME_COLUMN].astype(float).le(target_time + 1e-6)
            ]

            if not time_match.empty:
                row = time_match.iloc[0]

                cp = row["cp"]  # Power coefficient
                ct = row["cd"]  # Thrust Coefficient
                cq = row["ct"]  # Torque Coefficient

                blade_performance.extend([float(cp), float(ct), float(cq)])
            else:
                blade_performance.extend([0.0, 0.0, 0.0])

        except Exception as e:
            print(f"Error processing performance CSV {file_path}: {e}")
            blade_performance.extend([0.0, 0.0, 0.0])

    return blade_performance

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
        sess.num_blades = payload.meta.num_blades
        sess.num_nodes_per_blade = payload.meta.num_nodes_per_blade

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
        "last_outputs": sess.last_telemetry,  # Final data point
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

        # 1. Write dt (Solver starts calculation)
        write_step_to_fd(sess.step_fd, payload.dt)

        # 2. Update time optimistically (background task will verify)
        sess.t = payload.t + payload.dt
        sess.message = f"Advanced dt={payload.dt}. Waiting for STEPPED signal and file write..."

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
# Background Tasks (Perf Reader) - NOW INCLUDES CSV READING
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
                # Final, verified time (sent by solver in the STEPPED message)
                current_t = float(msg.get("time", sess.t))
                sess.t = current_t
                TARGET_N = sess.num_nodes_per_blade

                # --- CRITICAL: BLOCK and read data from CSVs ---
                try:
                    case_dir = Path(sess.case_dir)
                    current_t = float(msg.get("time", sess.t))
                    sess.t = current_t

                    loads_array = aggregate_loads_from_csv(case_dir, current_t)

                    # 1008 is used because it corresponds to 3 blades * 56 nodes/blade * 6 components
                    if len(loads_array) == 1008:
                        loads_array = downsample_loads(loads_array, target_nodes_per_blade=TARGET_N)

                    # --- FIX: Retrieve dimensions from the Session object ---
                    N = sess.num_nodes_per_blade
                    B = sess.num_blades

                    total_expected_size = B * N * 6

                    if len(loads_array) == total_expected_size:
                        # Convert the flat list into a list of 6-element lists (the required 2D array structure)
                        reshaped_loads = [loads_array[i:i + 6] for i in range(0, len(loads_array), 6)]

                        # Store the reshaped 2D list/array structure
                        msg["meshFrcMom"] = reshaped_loads

                    else:
                        # Log error and return empty data
                        print(
                            f"ERROR: Final loads array size mismatch. Expected {total_expected_size}, got {len(loads_array)}. Check CSV files."
                        )
                        msg["meshFrcMom"] = []

                except Exception as e:
                    print(f"WARNING: CSV reading failed: {e}")
                    msg["meshFrcMom"] = []

                try:
                    blade_performance = aggregate_performance_from_csv(case_dir, current_t)
                    expected_performance_size = 3  # cp, ct, cq

                    if len(blade_performance) == expected_performance_size:

                        # Store the reshaped 2D list/array structure
                        msg["bladePerformance"] = blade_performance
                    else:
                        print(
                            f"ERROR: Blade performance array size mismatch. Expected {expected_performance_size}, got {len(blade_performance)}. Check CSV files."
                        )
                        msg["bladePerformance"] = []
                except Exception as e:
                    print(f"WARNING: Performance CSV reading failed: {e}")
                    msg["bladePerformance"] = []

                # Store the final telemetry (includes meshFrcMom)
                sess.last_telemetry = msg

                sess.state = State.ready
                sess.message = f"Step complete. t={sess.t:.3f} (Loads read from CSVs)"
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
    os.chmod(step, 0o666)

    perf = case_dir / "perf.pipe"
    if perf.exists():
        perf.unlink()
    os.mkfifo(perf, 0o666)
    os.chmod(perf, 0o666)


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


def downsample_loads(flat_loads_1008: List[float], target_nodes_per_blade: int = 9) -> List[float]:
    """
    Downsamples the 3-blade x 56-node load array (1008 components) to the
    required (3 * 9 = 27) nodes (162 components) by averaging nodes into bins.

    Args:
        flat_loads_1008: The 1008-component list [F1x, F1y, F1z, M1x, ... F168z].
        target_nodes_per_blade: The desired node count per blade (usually 9).

    Returns:
        A flattened list of (3 * 9 * 6) = 162 components.
    """
    # 1. Reshape the 1008 array into (168 total nodes, 6 components)
    raw_array = np.array(flat_loads_1008).reshape(3, 56, 6)

    downsampled_loads = []

    # Source dimensions
    NUM_BLADES = 3
    SOURCE_NODES = 56

    # Calculate bin size
    bin_size = int(np.ceil(SOURCE_NODES / target_nodes_per_blade))  # 56 / 9 ≈ 6.22 -> 7 nodes per bin

    for b in range(NUM_BLADES):
        blade_data = raw_array[b]  # (56, 6) array

        for t in range(target_nodes_per_blade):
            # Define the slice for the current bin
            start_index = t * bin_size
            end_index = min((t + 1) * bin_size, SOURCE_NODES)

            # Select the nodes in the current bin
            bin_slice = blade_data[start_index:end_index, :]

            if bin_slice.size > 0:
                # 2. Average the forces/moments within the bin
                avg_load_vector = np.mean(bin_slice, axis=0)

                # 3. Flatten and append the 6 components
                downsampled_loads.extend(avg_load_vector.tolist())
            else:
                downsampled_loads.extend([0.0] * 6)  # Should only happen if calculation is wrong

    return downsampled_loads
