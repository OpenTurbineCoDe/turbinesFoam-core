from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any
import uuid

app = FastAPI()
SESS: Dict[str, Dict[str, Any]] = {}


class Meta(BaseModel):
    schema: str
    num_blades: int
    num_nodes_per_blade: int


class R6(BaseModel):  # 6
    __root__: List[float]


class R9(BaseModel):  # 9
    __root__: List[float]


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


@app.post("/initialize")
def initialize(payload: InitializeIn):
    sid = str(uuid.uuid4())
    SESS[sid] = {"meta": payload.meta.dict(), "constants": payload.constants, "state": payload.initial_state.dict()}
    return {"status": "ok", "session_id": sid, "channels": {"names": [], "units": []}}


@app.post("/step")
def step(payload: StepIn):
    sid = payload.session_id
    sess = SESS.get(sid)
    if not sess:
        return {"status": "error", "message": "invalid session_id"}

    B = payload.inputs.meta.num_blades
    N = payload.inputs.meta.num_nodes_per_blade
    BN = B * N

    # TODO: plug turbinesFoam here using sess["state"] + payload.inputs + constants
    meshFrcMom = [[0.0, 0.0, 0.0, 0.0, 0.0, 0.0] for _ in range(BN)]

    # update session state if you keep a history
    sess["state"] = {
        "t0": payload.t,
        "hub": payload.inputs.hub.dict(),
        "nacelle": payload.inputs.nacelle.dict(),
        "root": payload.inputs.root.dict(),
        "mesh": payload.inputs.mesh.dict(),
    }
    return {"status": "ok", "outputs": {"meshFrcMom": meshFrcMom}}


@app.post("/terminate")
def terminate(payload: Dict[str, str]):
    sid = payload.get("session_id")
    SESS.pop(sid, None)
    return {"status": "ok"}
