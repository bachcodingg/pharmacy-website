from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_admin
from app.db import get_connection, row_to_dict

router = APIRouter(prefix="/api/admin/coupons", tags=["admin-coupons"])


def _serialize(row: dict) -> dict:
    return {"code": row["code"], "kind": row["kind"], "value": row["value"], "active": bool(row["active"])}


@router.get("")
def list_coupons(admin: dict = Depends(get_current_admin)):
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM discount_codes ORDER BY code").fetchall()
    return [_serialize(row_to_dict(r)) for r in rows]


class CreateCouponRequest(BaseModel):
    code: str
    kind: str = Field(pattern="^(percent|fixed)$")
    value: int = Field(gt=0)


@router.post("", status_code=201)
def create_coupon(body: CreateCouponRequest, admin: dict = Depends(get_current_admin)):
    code = body.code.strip().upper()
    if body.kind == "percent" and body.value > 100:
        raise HTTPException(status_code=400, detail="A percent discount can't exceed 100")
    with get_connection() as conn:
        existing = conn.execute("SELECT code FROM discount_codes WHERE code = ?", (code,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="A coupon with this code already exists")
        conn.execute(
            "INSERT INTO discount_codes (code, kind, value, active) VALUES (?, ?, ?, 1)",
            (code, body.kind, body.value),
        )
        row = conn.execute("SELECT * FROM discount_codes WHERE code = ?", (code,)).fetchone()
    return _serialize(row_to_dict(row))


class SetActiveRequest(BaseModel):
    active: bool


@router.put("/{code}")
def set_coupon_active(code: str, body: SetActiveRequest, admin: dict = Depends(get_current_admin)):
    code = code.strip().upper()
    with get_connection() as conn:
        existing = conn.execute("SELECT code FROM discount_codes WHERE code = ?", (code,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Coupon not found")
        conn.execute("UPDATE discount_codes SET active = ? WHERE code = ?", (int(body.active), code))
        row = conn.execute("SELECT * FROM discount_codes WHERE code = ?", (code,)).fetchone()
    return _serialize(row_to_dict(row))
