import hashlib
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr

from app.db import get_connection, row_to_dict

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)

SESSION_TTL_SECONDS = 30 * 24 * 3600
RESET_TOKEN_TTL_SECONDS = 3600
PBKDF2_ITERATIONS = 390_000


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return salt.hex(), derived.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    _, derived_hex = hash_password(password, bytes.fromhex(salt_hex))
    return secrets.compare_digest(derived_hex, hash_hex)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = credentials.credentials
    with get_connection() as conn:
        row = conn.execute(
            "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id "
            "WHERE sessions.token = ? AND sessions.expires_at > ?",
            (token, time.time()),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return row_to_dict(row)


def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def public_user(user: dict) -> dict:
    return {"id": user["id"], "email": user["email"], "name": user["name"], "is_admin": bool(user.get("is_admin"))}


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    email: EmailStr | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class AddressRequest(BaseModel):
    label: str
    recipient_name: str
    phone: str
    line1: str
    line2: str | None = None
    city: str
    is_default: bool = False


@router.post("/register", status_code=201)
def register(body: RegisterRequest):
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    salt_hex, hash_hex = hash_password(body.password)
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (body.email,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, salt, name, created_at) VALUES (?, ?, ?, ?, ?)",
            (body.email, hash_hex, salt_hex, body.name, time.time()),
        )
        user_id = cursor.lastrowid
        token = _create_session(conn, user_id)
    return {"token": token, "user": {"id": user_id, "email": body.email, "name": body.name}}


@router.post("/login")
def login(body: LoginRequest):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (body.email,)).fetchone()
        if not row or not verify_password(body.password, row["salt"], row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        token = _create_session(conn, row["id"])
    return {"token": token, "user": public_user(row_to_dict(row))}


@router.post("/logout")
def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if credentials:
        with get_connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (credentials.credentials,))
    return {"status": "logged_out"}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return public_user(user)


@router.put("/me")
def update_profile(body: UpdateProfileRequest, user: dict = Depends(get_current_user)):
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.email is not None:
        updates["email"] = body.email
    if not updates:
        return public_user(user)
    with get_connection() as conn:
        if "email" in updates:
            clash = conn.execute(
                "SELECT id FROM users WHERE email = ? AND id != ?", (updates["email"], user["id"])
            ).fetchone()
            if clash:
                raise HTTPException(status_code=409, detail="Another account already uses this email")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", (*updates.values(), user["id"]))
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    return public_user(row_to_dict(row))


@router.post("/change-password")
def change_password(body: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    if not verify_password(body.old_password, user["salt"], user["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    salt_hex, hash_hex = hash_password(body.new_password)
    with get_connection() as conn:
        conn.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (hash_hex, salt_hex, user["id"]))
    return {"status": "password_changed"}


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest):
    """Generates a reset token. There is no email service wired up yet, so the
    token is returned directly in the response instead of being emailed - this
    endpoint is safe for local development only. Before this goes anywhere near
    production, swap the return value for an actual email send and stop
    returning the token to the caller."""
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (body.email,)).fetchone()
        if not row:
            return {"status": "if_the_email_exists_a_reset_link_was_sent"}
        token = secrets.token_urlsafe(32)
        now = time.time()
        conn.execute(
            "INSERT INTO password_reset_tokens (token, user_id, created_at, expires_at, used) VALUES (?, ?, ?, ?, 0)",
            (token, row["id"], now, now + RESET_TOKEN_TTL_SECONDS),
        )
    return {"status": "if_the_email_exists_a_reset_link_was_sent", "dev_only_reset_token": token}


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM password_reset_tokens WHERE token = ? AND used = 0 AND expires_at > ?",
            (body.token, time.time()),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="Reset token is invalid or expired")
        if len(body.new_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        salt_hex, hash_hex = hash_password(body.new_password)
        conn.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (hash_hex, salt_hex, row["user_id"]))
        conn.execute("UPDATE password_reset_tokens SET used = 1 WHERE token = ?", (body.token,))
    return {"status": "password_reset"}


@router.get("/addresses")
def list_addresses(user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM addresses WHERE user_id = ? ORDER BY is_default DESC, id", (user["id"],)).fetchall()
    return [row_to_dict(r) for r in rows]


@router.post("/addresses", status_code=201)
def create_address(body: AddressRequest, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        if body.is_default:
            conn.execute("UPDATE addresses SET is_default = 0 WHERE user_id = ?", (user["id"],))
        cursor = conn.execute(
            "INSERT INTO addresses (user_id, label, recipient_name, phone, line1, line2, city, is_default) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user["id"], body.label, body.recipient_name, body.phone, body.line1, body.line2, body.city, int(body.is_default)),
        )
        row = conn.execute("SELECT * FROM addresses WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row)


@router.delete("/addresses/{address_id}")
def delete_address(address_id: int, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM addresses WHERE id = ? AND user_id = ?", (address_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Address not found")
        conn.execute("DELETE FROM addresses WHERE id = ?", (address_id,))
    return {"status": "deleted"}


def _create_session(conn, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, now, now + SESSION_TTL_SECONDS),
    )
    return token
