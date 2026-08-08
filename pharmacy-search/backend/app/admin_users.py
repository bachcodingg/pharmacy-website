from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_admin
from app.db import get_connection, row_to_dict

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


def _serialize(row: dict) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "is_admin": bool(row["is_admin"]),
        "created_at": row["created_at"],
        "order_count": row.get("order_count", 0),
    }


@router.get("")
def list_users(admin: dict = Depends(get_current_admin)):
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT users.*, COUNT(orders.id) AS order_count
               FROM users LEFT JOIN orders ON orders.user_id = users.id
               GROUP BY users.id ORDER BY users.created_at DESC"""
        ).fetchall()
    return [_serialize(row_to_dict(r)) for r in rows]


class SetAdminRequest(BaseModel):
    is_admin: bool


@router.put("/{user_id}/admin")
def set_admin(user_id: int, body: SetAdminRequest, admin: dict = Depends(get_current_admin)):
    if user_id == admin["id"] and not body.is_admin:
        raise HTTPException(status_code=400, detail="You can't remove your own admin access")
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="User not found")
        conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (int(body.is_admin), user_id))
        row = conn.execute(
            """SELECT users.*, COUNT(orders.id) AS order_count
               FROM users LEFT JOIN orders ON orders.user_id = users.id
               WHERE users.id = ? GROUP BY users.id""",
            (user_id,),
        ).fetchone()
    return _serialize(row_to_dict(row))
