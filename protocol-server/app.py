from typing import List, Dict, Any, Optional
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field
import time
import glob
import re

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field, ConfigDict, RootModel

import pandas as pd
import numpy as np

from pathing import FOAM_RUN, FOAM_BASHRC
import utils as util
from file_generator import FileGenerator
from turbine_model import TurbineModel
import errno
import selectors
import json

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
    last_telemetry: Optional[Dict[str, Any]] = None
    num_blades: int = 0
    num_nodes_per_blade: int = 0
    tip_speed_ratio: float = 0.0
    last_inputs: Optional[Any] = None
    force_mapping_matrix: Optional[np.ndarray] = None

    # Dynamics Constants Extracted at runtime
    u_inf: float = 12.8
    rho: float = 1.225
    r_tip: float = 121.13
    ax_x: float = 0.9945
    ax_y: float = 0.0
    ax_z: float = -0.1045


SESS: Dict[str, Session] = {}


# ---------------------------
# Pydantic models
# ---------------------------


class Meta(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_name: str = Field(alias="schema")
    num_blades: int
    num_nodes_per_blade: int
    tip_speed_ratio: float


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
        self.tilt_angle = 0


# ---------------------------
# DATA AGGREGATION HELPERS
# ---------------------------


def extract_fvoptions_constants(case_dir: Path):
    """Extracts analytical constants dynamically from the fvOptions file."""
    fvoptions_path = case_dir / "system" / "fvOptions"
    if not fvoptions_path.exists():
        return 12.8, 1.225, 121.13, 0.9945, 0.0, -0.1045

    with open(fvoptions_path, "r") as f:
        content = f.read()

    vel_match = re.search(r"freeStreamVelocity\s+\(\s*([0-9.-]+)\s+[0-9.-]+\s+[0-9.-]+\s*\);", content)
    u_inf = float(vel_match.group(1)) if vel_match else 12.8

    rho_match = re.search(r"density\s+([0-9.]+);", content)
    rho = float(rho_match.group(1)) if rho_match else 1.225

    r_match = re.search(r"rotorRadius\s+([0-9.]+);", content)
    r_tip = float(r_match.group(1)) if r_match else 121.13

    # Extract the exact 3D rotation axis vector
    axis_match = re.search(r"axis\s+\(\s*([0-9.-]+)\s+([0-9.-]+)\s+([0-9.-]+)\s*\);", content)
    if axis_match:
        ax_x = float(axis_match.group(1))
        ax_y = float(axis_match.group(2))
        ax_z = float(axis_match.group(3))
    else:
        ax_x, ax_y, ax_z = 0.9945, 0.0, -0.1045

    return u_inf, rho, r_tip, ax_x, ax_y, ax_z


def aggregate_loads_from_csv(case_dir: Path, target_time: float) -> pd.DataFrame:
    LOADS_DIR = case_dir / "postProcessing" / "actuatorLineElements" / "0"
    if not LOADS_DIR.exists():
        return pd.DataFrame()

    file_pattern = str(LOADS_DIR / "turbine.blade*.element*.csv")
    load_files = sorted(glob.glob(file_pattern))
    if not load_files:
        return pd.DataFrame()

    debug_rows = []
    for file_path in load_files:
        try:
            filename = os.path.basename(file_path)
            blade_num = int(filename.split(".blade")[1].split(".element")[0])
            node_num = int(filename.split(".element")[1].split(".csv")[0])

            df = pd.read_csv(file_path)
            time_match = df[
                df["time"].astype(float).ge(target_time - 1e-6) & df["time"].astype(float).le(target_time + 1e-6)
            ]

            if not time_match.empty:
                row = time_match.iloc[0]
                debug_rows.append(
                    {
                        "blade": blade_num,
                        "node": node_num,
                        "time": float(row["time"]),
                        "fx": float(row["fx"]),
                        "fy": float(row["fy"]),
                        "fz": float(row["fz"]),
                    }
                )
        except Exception:
            pass

    return pd.DataFrame(debug_rows) if debug_rows else pd.DataFrame(columns=["blade", "node", "time", "fx", "fy", "fz"])


def aggregate_positions_from_csv(case_dir: Path, target_time: float) -> pd.DataFrame:
    POS_DIR = case_dir / "postProcessing" / "actuatorLineElements" / "0"
    if not POS_DIR.exists():
        return pd.DataFrame()

    file_pattern = str(POS_DIR / "turbine.blade*.element*.csv")
    pos_files = sorted(glob.glob(file_pattern))
    if not pos_files:
        return pd.DataFrame()

    debug_rows = []
    for file_path in pos_files:
        try:
            filename = os.path.basename(file_path)
            blade_num = int(filename.split(".blade")[1].split(".element")[0])
            node_num = int(filename.split(".element")[1].split(".csv")[0])

            df = pd.read_csv(file_path)
            time_match = df[
                df["time"].astype(float).ge(target_time - 1e-6) & df["time"].astype(float).le(target_time + 1e-6)
            ]

            if not time_match.empty:
                row = time_match.iloc[0]
                debug_rows.append(
                    {
                        "blade": blade_num,
                        "node": node_num,
                        "time": float(row["time"]),
                        "x": float(row["x"]),
                        "y": float(row["y"]),
                        "z": float(row["z"]),
                    }
                )
        except Exception:
            pass

    return pd.DataFrame(debug_rows) if debug_rows else pd.DataFrame(columns=["blade", "node", "time", "x", "y", "z"])


def aggregate_performance_from_csv(case_dir: Path, target_time: float) -> List[float]:
    PERF_DIR = case_dir / "postProcessing" / "turbines" / "0"
    if not PERF_DIR.exists():
        return []

    file_pattern = str(PERF_DIR / "turbine.csv")
    perf_files = sorted(glob.glob(file_pattern))
    if not perf_files:
        return []

    blade_performance = []
    for file_path in perf_files:
        try:
            df = pd.read_csv(file_path)
            time_match = df[
                df["time"].astype(float).ge(target_time - 1e-6) & df["time"].astype(float).le(target_time + 1e-6)
            ]

            if not time_match.empty:
                row = time_match.iloc[0]
                blade_performance.extend([float(row["cp"]), float(row["cd"]), float(row["ct"])])
            else:
                blade_performance.extend([0.0, 0.0, 0.0])
        except Exception:
            blade_performance.extend([0.0, 0.0, 0.0])

    return blade_performance


# ---------------------------
# RESAMPLING HELPERS
# ---------------------------


def get_bin_bounds(radii: np.ndarray) -> np.ndarray:
    if len(radii) == 0:
        return np.array([])
    bounds = np.zeros(len(radii) + 1)
    bounds[1:-1] = (radii[:-1] + radii[1:]) / 2.0
    if len(radii) > 1:
        bounds[0] = max(0.0, radii[0] - (radii[1] - radii[0]) / 2.0)
        bounds[-1] = radii[-1] + (radii[-1] - radii[-2]) / 2.0
    else:
        bounds[0] = 0.0
        bounds[-1] = radii[0] * 2.0
    return bounds


def build_mapping_matrix(r_source: np.ndarray, r_target: np.ndarray) -> np.ndarray:
    n_source = len(r_source)
    n_target = len(r_target)
    W = np.zeros((n_target, n_source))

    src_bounds = get_bin_bounds(r_source)
    tgt_bounds = get_bin_bounds(r_target)

    for i in range(n_target):
        r_start_tgt = tgt_bounds[i]
        r_end_tgt = tgt_bounds[i + 1]
        for j in range(n_source):
            r_start_src = src_bounds[j]
            r_end_src = src_bounds[j + 1]

            overlap_start = max(r_start_tgt, r_start_src)
            overlap_end = min(r_end_tgt, r_end_src)
            overlap_length = max(0.0, overlap_end - overlap_start)

            src_length = r_end_src - r_start_src
            if src_length > 0:
                W[i, j] = overlap_length / src_length

    return W


def fast_downsample_loads(loads_df: pd.DataFrame, W: np.ndarray, num_nodes: int) -> List[float]:
    downsampled_flat_list = []
    for blade_idx in [1, 2, 3]:
        if loads_df.empty:
            downsampled_flat_list.extend([0.0] * (num_nodes * 6))
            continue

        blade_loads = loads_df[loads_df["blade"] == blade_idx].sort_values("node")
        if blade_loads.empty or len(blade_loads) != W.shape[1]:
            downsampled_flat_list.extend([0.0] * (num_nodes * 6))
            continue

        source_forces = blade_loads[["fx", "fy", "fz"]].values
        target_forces = W @ source_forces

        for f_vec in target_forces:
            downsampled_flat_list.extend([float(f_vec[0]), float(f_vec[1]), float(f_vec[2]), 0.0, 0.0, 0.0])

    return downsampled_flat_list


# ---------------------------
# VERIFICATION LOGIC
# ---------------------------


def verify_performance_tolerances(
    sess: Session,
    current_t: float,
    cp: float,
    ct: float,
    cq: float,
    df_loads: pd.DataFrame,
    df_pos: pd.DataFrame,
    downsampled_forces_flat: List[float],
    target_pos: List[List[float]],
):
    """Calculates Analytical, Raw, and Downsampled Metrics, then flags deviances > 5%."""
    omega = sess.tip_speed_ratio * sess.u_inf / sess.r_tip
    A = np.pi * sess.r_tip**2
    q_dyn = 0.5 * sess.rho * A * (sess.u_inf**2)
    q_dyn_power = 0.5 * sess.rho * A * (sess.u_inf**3)

    # 1. Analytical (From Coefficients)
    ana_thrust = ct * q_dyn
    ana_torque = cq * q_dyn * sess.r_tip
    ana_power = cp * q_dyn_power

    # 2. Raw Integrated (df_loads already physically scaled inside the step event)
    if not df_loads.empty and not df_pos.empty:
        df_raw = pd.merge(df_loads, df_pos, on=["blade", "node"])
        raw_thrust = df_raw["fx"].sum()

        # Full 3D Moment (M = r x F) using pure global coordinates
        Mx = df_raw["y"] * df_raw["fz"] - df_raw["z"] * df_raw["fy"]
        My = df_raw["z"] * df_raw["fx"] - df_raw["x"] * df_raw["fz"]
        Mz = df_raw["x"] * df_raw["fy"] - df_raw["y"] * df_raw["fx"]

        Total_Mx = Mx.sum()
        Total_My = My.sum()
        Total_Mz = Mz.sum()

        # Pure dot product with the rotation axis vector extracted from fvOptions
        raw_torque = (Total_Mx * sess.ax_x) + (Total_My * sess.ax_y) + (Total_Mz * sess.ax_z)

        # Power correctly preserves the sign of the torque
        raw_power = raw_torque * omega
    else:
        raw_thrust = raw_torque = raw_power = 0.0

    # 3. Downsampled Integrated
    ds_thrust = ds_torque_x = ds_torque_y = ds_torque_z = 0.0
    num_nodes_total = len(target_pos)

    if len(downsampled_forces_flat) == num_nodes_total * 6:
        N = sess.num_nodes_per_blade

        # Determine the true hub origin by averaging the root nodes of all 3 blades
        if num_nodes_total >= 3 * N:
            t_hub_x = (target_pos[0][0] + target_pos[N][0] + target_pos[2 * N][0]) / 3.0
            t_hub_y = (target_pos[0][1] + target_pos[N][1] + target_pos[2 * N][1]) / 3.0
            t_hub_z = (target_pos[0][2] + target_pos[N][2] + target_pos[2 * N][2]) / 3.0
        else:
            t_hub_x = t_hub_y = t_hub_z = 0.0

        for i in range(num_nodes_total):
            # Calculate lever arm relative to the calculated downsampled hub
            x = target_pos[i][0] - t_hub_x
            y = target_pos[i][1] - t_hub_y
            z = target_pos[i][2] - t_hub_z

            fx = downsampled_forces_flat[i * 6 + 0]
            fy = downsampled_forces_flat[i * 6 + 1]
            fz = downsampled_forces_flat[i * 6 + 2]

            ds_thrust += fx
            ds_torque_x += y * fz - z * fy
            ds_torque_y += z * fx - x * fz
            ds_torque_z += x * fy - y * fx

        # Same pure dot product for Downsampled data
        ds_torque = (ds_torque_x * sess.ax_x) + (ds_torque_y * sess.ax_y) + (ds_torque_z * sess.ax_z)
        ds_power = ds_torque * omega
    else:
        ds_torque = ds_power = 0.0

    # Print Report
    print(f"\n--- Load Verification at t={current_t:.3f} ---")
    metrics = [
        ("Thrust [MN]", ana_thrust / 1e6, raw_thrust / 1e6, ds_thrust / 1e6),
        ("Torque [MNm]", ana_torque / 1e6, raw_torque / 1e6, ds_torque / 1e6),
        ("Power [MW]", ana_power / 1e6, raw_power / 1e6, ds_power / 1e6),
    ]

    print(
        f"{'Metric':<15} | {'Analytical':<12} | {'Raw Int':<12} | {'DS Int':<12} | {'Err(Raw)':<10} | {'Err(DS)':<10}"
    )
    print("-" * 80)
    for name, ana, raw, ds in metrics:
        if abs(ana) < 1e-6:
            continue
        err_raw = abs(ana - raw) / abs(ana) * 100
        err_ds = abs(ana - ds) / abs(ana) * 100

        flag_raw = " !!!" if err_raw > 5.0 else ""
        flag_ds = " !!!" if err_ds > 5.0 else ""

        print(
            f"{name:<15} | {ana:<12.3f} | {raw:<12.3f} | {ds:<12.3f} | {err_raw:<6.2f}%{flag_raw} | {err_ds:<6.2f}%{flag_ds}"
        )
    print("-" * 80, flush=True)


# ---------------------------
# API Endpoints
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
        sess.tip_speed_ratio = payload.meta.tip_speed_ratio

        # Load Analytical Constants dynamically
        u_inf, rho, r_tip, ax_x, ax_y, ax_z = extract_fvoptions_constants(case_dir)
        sess.u_inf = u_inf
        sess.rho = rho
        sess.r_tip = r_tip
        sess.ax_x = ax_x
        sess.ax_y = ax_y
        sess.ax_z = ax_z

        # 1. Start solver & reader
        proc = start_allrun(case_dir)
        sess.proc = proc
        background_tasks.add_task(_perf_reader_task, sid)

        # 2. Open persistent step writer
        sess.step_fd = open_step_writer(case_dir)

        # 3. UNBLOCK THE SOLVER'S INITIAL BLOCK
        os.write(sess.step_fd, "CONT\n".encode("ascii"))

        sess.message = "Solver launched. Waiting for READY signal..."
        _apply_op(sess)

    except Exception as e:
        sess.state = State.error
        sess.last_error = str(e)
        _apply_op(sess)


@app.post("/initialize", status_code=202)
def initialize(payload: InitializeIn, background_tasks: BackgroundTasks):
    sid = str(uuid.uuid4())
    util.make_directory_in_foam_run(sid)
    util.clear_case_directory(sid)
    util.copy_axial_turbine_case(sid)

    model = TurbineModel(name="IEA_15MW_AB_OF")
    model.read_from_yaml()
    run_opts = RunOptions()
    run_opts.tip_speed_ratio = payload.meta.tip_speed_ratio
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
        "last_outputs": sess.last_telemetry,
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

    background_tasks.add_task(_do_step, sid, payload, sess.op_seq)
    return _ack(sid, sess)


def _do_step(sid: str, payload: StepIn, op_seq: int):
    sess = SESS.get(sid)
    if not sess or sess.op_seq != op_seq:
        return
    try:
        if sess.step_fd is None:
            raise RuntimeError("Step FD was not initialized.")
        sess.last_inputs = payload.inputs

        write_step_to_fd(sess.step_fd, payload.dt)
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

    sess.state = State.terminating
    _apply_op(sess)
    background_tasks.add_task(_do_terminate, sid, sess.op_seq)
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
    finally:
        SESS.pop(sid, None)


# ---------------------------
# Background Task
# ---------------------------


def _open_perf_reader(case_dir: Path):
    perf_path = case_dir / "perf.pipe"
    fd = os.open(perf_path, os.O_RDONLY | os.O_NONBLOCK)
    return os.fdopen(fd, "r", buffering=1)


def _perf_reader_task(sid: str):
    sess = SESS.get(sid)
    if not sess:
        return
    case_dir = Path(sess.case_dir)

    try:
        fh = _open_perf_reader(case_dir)
    except Exception:
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
                try:
                    case_dir = Path(sess.case_dir)
                    current_t = float(msg.get("time", sess.t))
                    sess.t = current_t
                    N = sess.num_nodes_per_blade
                    B = sess.num_blades

                    # 1. Load Element Data & Scale from Kinematic to Physical Forces
                    loads_df = aggregate_loads_from_csv(case_dir, current_t)
                    if not loads_df.empty:
                        loads_df["fx"] *= sess.rho
                        loads_df["fy"] *= sess.rho
                        loads_df["fz"] *= sess.rho

                    # 2. Get Element Positions (Required to calculate local Moment Arms)
                    positions_df = aggregate_positions_from_csv(case_dir, current_t)

                    # 3. ONE-TIME MATRIX CALCULATION
                    if sess.force_mapping_matrix is None and sess.last_inputs is not None:
                        if not positions_df.empty:
                            b1_pos = positions_df[positions_df["blade"] == 1].sort_values("node")
                            src_pos = b1_pos[["x", "y", "z"]].values
                            root_pos = np.array(sess.last_inputs.root.pos[0])
                            tgt_pos = np.array(sess.last_inputs.mesh.pos[0:N])

                            r_source = np.linalg.norm(src_pos - root_pos, axis=1)
                            r_target = np.linalg.norm(tgt_pos - root_pos, axis=1)
                            sess.force_mapping_matrix = build_mapping_matrix(r_source, r_target)

                    # 4. FAST DOWNSAMPLING (Inherits the Density Scale)
                    if sess.force_mapping_matrix is not None:
                        loads_flat_list = fast_downsample_loads(loads_df, sess.force_mapping_matrix, N)
                    else:
                        loads_flat_list = []

                    total_expected_size = B * N * 6
                    if len(loads_flat_list) == total_expected_size:
                        reshaped_loads = [loads_flat_list[i : i + 6] for i in range(0, len(loads_flat_list), 6)]
                        msg["meshFrcMom"] = reshaped_loads
                    else:
                        msg["meshFrcMom"] = []

                    if sess.last_inputs is not None:
                        msg["positions"] = sess.last_inputs.mesh.pos
                    else:
                        msg["positions"] = []

                    # 5. Extract Analytical Values
                    blade_performance = aggregate_performance_from_csv(case_dir, current_t)
                    msg["bladePerformance"] = blade_performance

                    # 6. VERIFICATION (Check < 5% Tolerance)
                    if sess.last_inputs is not None and len(blade_performance) == 3:
                        verify_performance_tolerances(
                            sess=sess,
                            current_t=current_t,
                            cp=blade_performance[0],
                            ct=blade_performance[1],
                            cq=blade_performance[2],
                            df_loads=loads_df,
                            df_pos=positions_df,
                            downsampled_forces_flat=loads_flat_list,
                            target_pos=sess.last_inputs.mesh.pos,
                        )

                except Exception as e:
                    print(f"WARNING: Fast downsampling failed: {e}", flush=True)
                    msg["meshFrcMom"] = []
                    msg["positions"] = []

                sess.last_telemetry = msg
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
