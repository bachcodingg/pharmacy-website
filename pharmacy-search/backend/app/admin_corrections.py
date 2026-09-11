import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_admin
from app.db import get_connection, record_admin_action

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from learning.review import load, save, set_status, CANDIDATES_PATH  # noqa: E402

router = APIRouter(prefix="/api/admin/corrections", tags=["admin-corrections"])


@router.get("")
def list_corrections(admin: dict = Depends(get_current_admin)):
    """Same data learning/review.py's CLI reads - this is that same
    pharmacist-approval gate, just as a web page instead of a terminal."""
    return load(CANDIDATES_PATH)


class DecisionRequest(BaseModel):
    from_query: str
    to_query: str


@router.post("/approve")
def approve(body: DecisionRequest, admin: dict = Depends(get_current_admin)):
    candidates = load(CANDIDATES_PATH)
    match = next((c for c in candidates if c["from_query"] == body.from_query and c["to_query"] == body.to_query), None)
    if not match:
        raise HTTPException(status_code=404, detail="No candidate pair found for that from/to query")
    set_status(body.from_query, body.to_query, "approved")
    with get_connection() as conn:
        record_admin_action(conn, admin["id"], "correction_approve", "correction_pair", None,
                            {"from_query": body.from_query, "to_query": body.to_query})
    return {"status": "approved", "note": "Run build/build_nearmiss.py to apply it to the live search index."}


@router.post("/reject")
def reject(body: DecisionRequest, admin: dict = Depends(get_current_admin)):
    candidates = load(CANDIDATES_PATH)
    match = next((c for c in candidates if c["from_query"] == body.from_query and c["to_query"] == body.to_query), None)
    if not match:
        raise HTTPException(status_code=404, detail="No candidate pair found for that from/to query")
    set_status(body.from_query, body.to_query, "rejected")
    return {"status": "rejected"}
