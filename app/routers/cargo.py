from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CargoHandoff, CargoItem, User, iso
from ..security import current_user, require_roles
from ..serializers import cargo_dict
from ..services import rules, sync

router = APIRouter(prefix="/api/cargo", tags=["cargo"], dependencies=[Depends(current_user)])


class HandoffIn(BaseModel):
    to_node: str


@router.get("")
def cargo(consignment: Optional[str] = None, status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(CargoItem)
    if consignment:
        q = q.filter(CargoItem.consignment == consignment)
    if status:
        q = q.filter(CargoItem.status == status)
    rows = q.order_by(CargoItem.consignment, CargoItem.id).all()
    consignments = sorted({r.consignment for r in db.query(CargoItem.consignment).distinct()}) if not consignment else [consignment]
    return {"items": [cargo_dict(c) for c in rows], "consignments": consignments}


@router.get("/rules")
def cargo_rules():
    return rules.rules()


@router.get("/consignments/{cid}/check")
def check(cid: str, db: Session = Depends(get_db)):
    items = db.query(CargoItem).filter(CargoItem.consignment == cid).all()
    if not items:
        raise HTTPException(404, "Unknown consignment")
    return {"consignment": cid, **rules.check_consignment(items)}


@router.get("/{cid}/history")
def history(cid: str, db: Session = Depends(get_db)):
    rows = db.query(CargoHandoff).filter(CargoHandoff.cargo_id == cid).order_by(CargoHandoff.at).all()
    return [{"from": h.from_node, "to": h.to_node, "at": iso(h.at), "by": h.username, "device": h.device_id} for h in rows]


@router.post("/{cid}/handoff")
def handoff(cid: str, body: HandoffIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*sync.EVENT_ROLES["HANDOFF"]))):
    if db.get(CargoItem, cid) is None:
        raise HTTPException(404, "Unknown cargo item")
    res = sync.submit(db, user, "HANDOFF", cid, {"cargo_id": cid, "to_node": body.to_node})
    if res["status"] == "rejected":
        raise HTTPException(409, res["reason"])
    return cargo_dict(db.get(CargoItem, cid))
