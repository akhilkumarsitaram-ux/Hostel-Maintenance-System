"""SQLite database models and data access for the hostel maintenance system."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from werkzeug.security import check_password_hash, generate_password_hash

# --- Constants ---

ROLES = ("resident", "staff", "admin")
CATEGORIES = ("Electrical", "Plumbing", "Cleaning", "Furniture", "Other")
PRIORITIES = ("Low", "Medium", "High", "Urgent")
STATUSES = ("Submitted", "Assigned", "In Progress", "Resolved", "Closed")

RESIDENT_ALLOWED_STATUSES: frozenset[str] = frozenset()
STAFF_ALLOWED_STATUSES: frozenset[str] = frozenset({"In Progress", "Resolved"})
ADMIN_ALLOWED_STATUSES: frozenset[str] = frozenset(STATUSES)

# Valid status transitions: from_status -> set of allowed to_status
STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "Submitted": frozenset({"Assigned", "Closed"}),
    "Assigned": frozenset({"In Progress", "Closed", "Submitted"}),
    "In Progress": frozenset({"Resolved", "Closed", "Assigned"}),
    "Resolved": frozenset({"Closed", "In Progress"}),
    "Closed": frozenset({"Submitted", "Assigned", "In Progress"}),
}


def utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_database_path() -> Path:
    """Resolve DATABASE_PATH from environment; create parent directory if needed."""
    raw = os.environ.get("DATABASE_PATH", "data/hostel_maintenance.db")
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path if db_path is not None else get_database_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    conn = _connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def check_database_connection(db_path: Path | None = None) -> bool:
    """Return True if the database is reachable."""
    try:
        with get_db(db_path) as conn:
            conn.execute("SELECT 1")
        return True
    except sqlite3.Error:
        return False


def init_db(db_path: Path | None = None) -> None:
    """
    Create database schema if tables do not exist.
    Does not drop or truncate existing data.
    """
    with get_db(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('resident', 'staff', 'admin')),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resident_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                hostel TEXT NOT NULL,
                room_number TEXT NOT NULL,
                priority TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Submitted',
                assigned_staff_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (resident_id) REFERENCES users(id),
                FOREIGN KEY (assigned_staff_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS complaint_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id INTEGER NOT NULL,
                updated_by INTEGER NOT NULL,
                old_status TEXT,
                new_status TEXT,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (complaint_id) REFERENCES complaints(id),
                FOREIGN KEY (updated_by) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_complaints_resident ON complaints(resident_id);
            CREATE INDEX IF NOT EXISTS idx_complaints_staff ON complaints(assigned_staff_id);
            CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);
            CREATE INDEX IF NOT EXISTS idx_updates_complaint ON complaint_updates(complaint_id);
            """
        )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


# --- Users ---


def get_user_by_username(username: str, db_path: Path | None = None) -> dict[str, Any] | None:
    with get_db(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, username, password_hash, full_name, role, created_at
            FROM users WHERE username = ?
            """,
            (username.strip(),),
        ).fetchone()
    return row_to_dict(row)


def get_user_by_id(user_id: int, db_path: Path | None = None) -> dict[str, Any] | None:
    with get_db(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, username, password_hash, full_name, role, created_at
            FROM users WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
    return row_to_dict(row)


def create_user(
    username: str,
    password: str,
    full_name: str,
    role: str,
    db_path: Path | None = None,
) -> int | None:
    if role not in ROLES:
        return None
    now = utc_now_iso()
    pw_hash = generate_password_hash(password)
    try:
        with get_db(db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO users (username, password_hash, full_name, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (username.strip(), pw_hash, full_name.strip(), role, now),
            )
            return int(cur.lastrowid)
    except sqlite3.IntegrityError:
        return None


def verify_password(user: dict[str, Any], password: str) -> bool:
    return check_password_hash(user["password_hash"], password)


def list_staff_users(db_path: Path | None = None) -> list[dict[str, Any]]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, username, full_name, role, created_at
            FROM users WHERE role = 'staff' ORDER BY full_name
            """
        ).fetchall()
    return [dict(r) for r in rows]


def user_exists_with_role(user_id: int, role: str, db_path: Path | None = None) -> bool:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE id = ? AND role = ?",
            (user_id, role),
        ).fetchone()
    return row is not None


# --- Complaint updates history ---


def add_complaint_update(
    complaint_id: int,
    updated_by: int,
    note: str,
    old_status: str | None = None,
    new_status: str | None = None,
    db_path: Path | None = None,
) -> None:
    now = utc_now_iso()
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO complaint_updates
            (complaint_id, updated_by, old_status, new_status, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (complaint_id, updated_by, old_status, new_status, note.strip(), now),
        )


def get_complaint_updates(complaint_id: int, db_path: Path | None = None) -> list[dict[str, Any]]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT cu.id, cu.complaint_id, cu.updated_by, cu.old_status, cu.new_status,
                   cu.note, cu.created_at, u.full_name AS updater_name, u.role AS updater_role
            FROM complaint_updates cu
            JOIN users u ON u.id = cu.updated_by
            WHERE cu.complaint_id = ?
            ORDER BY cu.created_at ASC, cu.id ASC
            """,
            (complaint_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# --- Complaints ---


def create_complaint(
    resident_id: int,
    category: str,
    hostel: str,
    room_number: str,
    priority: str,
    description: str,
    db_path: Path | None = None,
) -> int | None:
    if category not in CATEGORIES or priority not in PRIORITIES:
        return None
    now = utc_now_iso()
    with get_db(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO complaints
            (resident_id, category, hostel, room_number, priority, description, status,
             assigned_staff_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'Submitted', NULL, ?, ?)
            """,
            (
                resident_id,
                category,
                hostel.strip(),
                room_number.strip(),
                priority,
                description.strip(),
                now,
                now,
            ),
        )
        complaint_id = int(cur.lastrowid)
    add_complaint_update(
        complaint_id,
        resident_id,
        "Complaint submitted.",
        old_status=None,
        new_status="Submitted",
        db_path=db_path,
    )
    return complaint_id


def get_complaint_by_id(complaint_id: int, db_path: Path | None = None) -> dict[str, Any] | None:
    with get_db(db_path) as conn:
        row = conn.execute(
            """
            SELECT c.*,
                   r.full_name AS resident_name, r.username AS resident_username,
                   s.full_name AS staff_name, s.username AS staff_username
            FROM complaints c
            JOIN users r ON r.id = c.resident_id
            LEFT JOIN users s ON s.id = c.assigned_staff_id
            WHERE c.id = ?
            """,
            (complaint_id,),
        ).fetchone()
    return row_to_dict(row)


def _complaint_filter_clause(
    *,
    resident_id: int | None = None,
    assigned_staff_id: int | None = None,
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    search: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if resident_id is not None:
        clauses.append("c.resident_id = ?")
        params.append(resident_id)
    if assigned_staff_id is not None:
        clauses.append("c.assigned_staff_id = ?")
        params.append(assigned_staff_id)
    if status:
        clauses.append("c.status = ?")
        params.append(status)
    if category:
        clauses.append("c.category = ?")
        params.append(category)
    if priority:
        clauses.append("c.priority = ?")
        params.append(priority)
    if search and search.strip():
        q = f"%{search.strip()}%"
        clauses.append(
            "(c.description LIKE ? OR c.hostel LIKE ? OR c.room_number LIKE ? OR c.category LIKE ?)"
        )
        params.extend([q, q, q, q])
    where = " AND ".join(clauses) if clauses else "1=1"
    return where, params


def list_complaints(
    *,
    resident_id: int | None = None,
    assigned_staff_id: int | None = None,
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    assigned_staff_filter: int | None = None,
    search: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    if assigned_staff_filter is not None:
        if assigned_staff_filter == 0:
            # Unassigned filter (admin)
            extra = " AND c.assigned_staff_id IS NULL"
            params_extra: list[Any] = []
        else:
            extra = " AND c.assigned_staff_id = ?"
            params_extra = [assigned_staff_filter]
    else:
        extra = ""
        params_extra = []

    where, params = _complaint_filter_clause(
        resident_id=resident_id,
        assigned_staff_id=assigned_staff_id,
        status=status,
        category=category,
        priority=priority,
        search=search,
    )
    sql = f"""
        SELECT c.*,
               r.full_name AS resident_name,
               s.full_name AS staff_name
        FROM complaints c
        JOIN users r ON r.id = c.resident_id
        LEFT JOIN users s ON s.id = c.assigned_staff_id
        WHERE {where}{extra}
        ORDER BY c.updated_at DESC, c.id DESC
    """
    with get_db(db_path) as conn:
        rows = conn.execute(sql, params + params_extra).fetchall()
    return [dict(r) for r in rows]


def admin_complaint_counts(db_path: Path | None = None) -> dict[str, int]:
    with get_db(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
        pending = conn.execute(
            """
            SELECT COUNT(*) FROM complaints
            WHERE status IN ('Submitted', 'Assigned')
            """
        ).fetchone()[0]
        in_progress = conn.execute(
            "SELECT COUNT(*) FROM complaints WHERE status = 'In Progress'"
        ).fetchone()[0]
        resolved = conn.execute(
            "SELECT COUNT(*) FROM complaints WHERE status IN ('Resolved', 'Closed')"
        ).fetchone()[0]
    return {
        "total": total,
        "pending": pending,
        "in_progress": in_progress,
        "resolved": resolved,
    }


def is_status_transition_allowed(current: str, new: str, role: str) -> bool:
    if new not in STATUSES:
        return False
    allowed_next = STATUS_TRANSITIONS.get(current, frozenset())
    if new not in allowed_next:
        return False
    if role == "resident":
        return new in RESIDENT_ALLOWED_STATUSES
    if role == "staff":
        return new in STAFF_ALLOWED_STATUSES
    if role == "admin":
        return new in ADMIN_ALLOWED_STATUSES
    return False


def complaint_is_editable_by_role(status: str, role: str) -> bool:
    if status == "Closed" and role in ("resident", "staff"):
        return False
    return True


def update_complaint_staff_status(
    complaint_id: int,
    staff_id: int,
    new_status: str,
    note: str,
    db_path: Path | None = None,
) -> tuple[bool, str]:
    complaint = get_complaint_by_id(complaint_id, db_path)
    if not complaint:
        return False, "Complaint not found."
    if complaint["assigned_staff_id"] != staff_id:
        return False, "Not assigned to you."
    if complaint["status"] == "Closed":
        return False, "Closed complaints cannot be edited."
    if not is_status_transition_allowed(complaint["status"], new_status, "staff"):
        return False, "Invalid status transition."
    if new_status not in STAFF_ALLOWED_STATUSES and new_status != complaint["status"]:
        return False, "Staff cannot set this status."
    if not note.strip():
        return False, "Please add a resolution note."
    old_status = complaint["status"]
    now = utc_now_iso()
    with get_db(db_path) as conn:
        conn.execute(
            "UPDATE complaints SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, complaint_id),
        )
    add_complaint_update(
        complaint_id,
        staff_id,
        note.strip(),
        old_status=old_status,
        new_status=new_status,
        db_path=db_path,
    )
    return True, "Status updated."


def admin_assign_complaint(
    complaint_id: int,
    admin_id: int,
    staff_id: int,
    db_path: Path | None = None,
) -> tuple[bool, str]:
    if not user_exists_with_role(staff_id, "staff", db_path):
        return False, "Invalid staff account."
    complaint = get_complaint_by_id(complaint_id, db_path)
    if not complaint:
        return False, "Complaint not found."
    old_status = complaint["status"]
    new_status = "Assigned"
    if old_status == "Closed":
        return False, "Cannot assign a closed complaint without reopening."
    now = utc_now_iso()
    with get_db(db_path) as conn:
        conn.execute(
            """
            UPDATE complaints
            SET assigned_staff_id = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (staff_id, new_status, now, complaint_id),
        )
    staff = get_user_by_id(staff_id, db_path)
    staff_name = staff["full_name"] if staff else str(staff_id)
    note = f"Assigned to staff: {staff_name}."
    add_complaint_update(
        complaint_id,
        admin_id,
        note,
        old_status=old_status if old_status != new_status else None,
        new_status=new_status if old_status != new_status else None,
        db_path=db_path,
    )
    return True, "Complaint assigned."


def admin_update_complaint(
    complaint_id: int,
    admin_id: int,
    *,
    new_status: str | None = None,
    new_priority: str | None = None,
    note: str = "",
    db_path: Path | None = None,
) -> tuple[bool, str]:
    complaint = get_complaint_by_id(complaint_id, db_path)
    if not complaint:
        return False, "Complaint not found."
    changes: list[str] = []
    old_status = complaint["status"]
    old_priority = complaint["priority"]
    status_to_set = old_status
    priority_to_set = old_priority

    if new_priority and new_priority in PRIORITIES and new_priority != old_priority:
        priority_to_set = new_priority
        changes.append(f"Priority changed from {old_priority} to {new_priority}.")

    if new_status and new_status != old_status:
        if not is_status_transition_allowed(old_status, new_status, "admin"):
            return False, "Invalid status transition."
        status_to_set = new_status
        changes.append(f"Status changed from {old_status} to {new_status}.")

    if not changes and not note.strip():
        return False, "No changes to save."

    final_note = note.strip() or " ".join(changes)
    now = utc_now_iso()
    with get_db(db_path) as conn:
        conn.execute(
            """
            UPDATE complaints SET status = ?, priority = ?, updated_at = ? WHERE id = ?
            """,
            (status_to_set, priority_to_set, now, complaint_id),
        )
    add_complaint_update(
        complaint_id,
        admin_id,
        final_note,
        old_status=old_status if status_to_set != old_status else None,
        new_status=status_to_set if status_to_set != old_status else None,
        db_path=db_path,
    )
    return True, "Complaint updated."


# --- Demo seed ---

DEMO_USERS = [
    ("resident1", "demo1234", "Alex Resident", "resident"),
    ("staff1", "demo1234", "Sam Maintenance", "staff"),
    ("staff2", "demo1234", "Jordan Technician", "staff"),
    ("admin1", "demo1234", "Casey Administrator", "admin"),
]


def seed_demo(db_path: Path | None = None) -> None:
    """Create demo users and sample complaints if they do not already exist."""
    init_db(db_path)
    user_ids: dict[str, int] = {}
    for username, password, full_name, role in DEMO_USERS:
        existing = get_user_by_username(username, db_path)
        if existing:
            user_ids[username] = existing["id"]
        else:
            uid = create_user(username, password, full_name, role, db_path)
            if uid:
                user_ids[username] = uid

    resident_id = user_ids.get("resident1")
    staff1_id = user_ids.get("staff1")
    staff2_id = user_ids.get("staff2")
    if not resident_id:
        return

    with get_db(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
    if count > 0:
        return

    samples = [
        (
            resident_id,
            "Electrical",
            "Clarks Hall",
            "204",
            "High",
            "Bedside lamp socket sparks when plugging in a charger.",
            "Submitted",
            None,
        ),
        (
            resident_id,
            "Plumbing",
            "Paul Kent Hall",
            "112",
            "Urgent",
            "Shower drain blocked; water pooling on bathroom floor.",
            "Assigned",
            staff1_id,
        ),
        (
            resident_id,
            "Cleaning",
            "Clarks Hall",
            "310",
            "Medium",
            "Common kitchen area needs deep cleaning after weekend event.",
            "In Progress",
            staff2_id,
        ),
        (
            resident_id,
            "Furniture",
            "Paul Kent Hall",
            "405",
            "Low",
            "Wardrobe door hinge loose and difficult to close.",
            "Resolved",
            staff1_id,
        ),
    ]
    admin_id = user_ids.get("admin1", resident_id)
    for (
        rid,
        category,
        hostel,
        room,
        priority,
        description,
        status,
        staff_id,
    ) in samples:
        now = utc_now_iso()
        with get_db(db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO complaints
                (resident_id, category, hostel, room_number, priority, description,
                 status, assigned_staff_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rid,
                    category,
                    hostel,
                    room,
                    priority,
                    description,
                    status,
                    staff_id,
                    now,
                    now,
                ),
            )
            cid = int(cur.lastrowid)
        add_complaint_update(
            cid,
            rid,
            "Sample complaint created for demonstration.",
            new_status="Submitted",
            db_path=db_path,
        )
        if staff_id and status != "Submitted":
            add_complaint_update(
                cid,
                admin_id,
                "Assigned to maintenance staff (demo data).",
                old_status="Submitted",
                new_status="Assigned",
                db_path=db_path,
            )
        if status in ("In Progress", "Resolved"):
            add_complaint_update(
                cid,
                staff_id or admin_id,
                "Work started on site (demo data).",
                old_status="Assigned",
                new_status="In Progress",
                db_path=db_path,
            )
        if status == "Resolved":
            add_complaint_update(
                cid,
                staff_id or admin_id,
                "Issue fixed; resident informed (demo data).",
                old_status="In Progress",
                new_status="Resolved",
                db_path=db_path,
            )
