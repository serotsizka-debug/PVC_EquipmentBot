import sqlite3
from datetime import datetime
from typing import Optional

from config import DB_PATH

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = connect()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        full_name TEXT,
        phone TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS equipment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        total_qty INTEGER NOT NULL DEFAULT 0,
        available_qty INTEGER NOT NULL DEFAULT 0,
        disabled INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        full_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        event_name TEXT NOT NULL,
        pickup_at TEXT NOT NULL,
        return_at TEXT NOT NULL,
        status TEXT NOT NULL,
        rules_agreed INTEGER NOT NULL DEFAULT 0,
        rules_agreed_at TEXT,
        rejection_reason TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS booking_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id INTEGER NOT NULL,
        equipment_id INTEGER NOT NULL,
        reserved_qty INTEGER NOT NULL,
        issued_qty INTEGER NOT NULL DEFAULT 0,
        returned_qty INTEGER NOT NULL DEFAULT 0,
        condition TEXT,
        comment TEXT,
        FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
        FOREIGN KEY (equipment_id) REFERENCES equipment(id)
    );

    CREATE INDEX IF NOT EXISTS idx_bookings_period
      ON bookings(status, pickup_at, return_at);

    CREATE INDEX IF NOT EXISTS idx_booking_items_booking
      ON booking_items(booking_id);
    """)
    conn.commit()
    conn.close()

def seed_equipment():
    items = [
        ("Стілець дерев'яний розкладний", 30),
        ("Намет Tera 2-місний", 3),
        ("Каремат", 20),
        ("Проектор", 1),
        ("Мікрофон безпровідний", 2),
        ("Рації", 5),
        ("Спальний мішок", 10),
    ]
    conn = connect()
    for name, qty in items:
        conn.execute(
            """INSERT OR IGNORE INTO equipment
               (name,total_qty,available_qty,created_at)
               VALUES (?,?,?,?)""",
            (name, qty, qty, datetime.now().isoformat()),
        )
    conn.commit()
    conn.close()

def upsert_user(telegram_id: int, full_name: Optional[str] = None, phone: Optional[str] = None):
    conn = connect()
    row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    if row:
        conn.execute(
            "UPDATE users SET full_name=COALESCE(?,full_name), phone=COALESCE(?,phone) WHERE telegram_id=?",
            (full_name, phone, telegram_id),
        )
    else:
        conn.execute(
            "INSERT INTO users(telegram_id,full_name,phone,created_at) VALUES(?,?,?,?)",
            (telegram_id, full_name, phone, datetime.now().isoformat()),
        )
    conn.commit()
    conn.close()

def get_user(telegram_id: int):
    conn = connect()
    row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    conn.close()
    return row

def get_equipment():
    conn = connect()
    rows = conn.execute("SELECT * FROM equipment ORDER BY id").fetchall()
    conn.close()
    return rows

def get_equipment_item(equipment_id: int):
    conn = connect()
    row = conn.execute("SELECT * FROM equipment WHERE id=?", (equipment_id,)).fetchone()
    conn.close()
    return row

def create_booking(telegram_id, full_name, phone, event_name, pickup_at, return_at, items, rules_agreed_at):
    conn = connect()
    now = datetime.now().isoformat()
    cur = conn.execute(
        """INSERT INTO bookings
        (telegram_id,full_name,phone,event_name,pickup_at,return_at,status,
         rules_agreed,rules_agreed_at,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (telegram_id, full_name, phone, event_name, pickup_at, return_at,
         "pending", 1, rules_agreed_at, now, now),
    )
    booking_id = cur.lastrowid
    for equipment_id, qty in items.items():
        conn.execute(
            "INSERT INTO booking_items(booking_id,equipment_id,reserved_qty) VALUES(?,?,?)",
            (booking_id, equipment_id, qty),
        )
    conn.commit()
    conn.close()
    return booking_id

def get_booking(booking_id: int):
    conn = connect()
    row = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    conn.close()
    return row

def get_booking_items(booking_id: int):
    conn = connect()
    rows = conn.execute(
        """SELECT bi.*, e.name AS equipment_name
           FROM booking_items bi
           JOIN equipment e ON e.id=bi.equipment_id
           WHERE bi.booking_id=?
           ORDER BY bi.id""",
        (booking_id,),
    ).fetchall()
    conn.close()
    return rows

def get_user_bookings(telegram_id: int):
    conn = connect()
    rows = conn.execute(
        """SELECT * FROM bookings
           WHERE telegram_id=?
           ORDER BY pickup_at DESC""",
        (telegram_id,),
    ).fetchall()
    conn.close()
    return rows

def update_booking_times(booking_id: int, pickup_at: str, return_at: str):
    conn = connect()
    conn.execute(
        "UPDATE bookings SET pickup_at=?,return_at=?,updated_at=? WHERE id=?",
        (pickup_at, return_at, datetime.now().isoformat(), booking_id),
    )
    conn.commit()
    conn.close()

def set_booking_status(booking_id: int, status: str, reason: Optional[str] = None):
    conn = connect()
    conn.execute(
        """UPDATE bookings
           SET status=?, rejection_reason=?, updated_at=?
           WHERE id=?""",
        (status, reason, datetime.now().isoformat(), booking_id),
    )
    conn.commit()
    conn.close()

def set_issue_quantities(booking_id: int, issued_by_item: dict):
    conn = connect()
    for item_id, qty in issued_by_item.items():
        row = conn.execute(
            """SELECT equipment_id, reserved_qty, issued_qty
               FROM booking_items WHERE id=? AND booking_id=?""",
            (item_id, booking_id),
        ).fetchone()
        if not row:
            continue
        # If fewer units are actually issued than reserved, release the difference.
        release = max(0, int(row["reserved_qty"]) - int(qty))
        if release:
            conn.execute(
                "UPDATE equipment SET available_qty=available_qty+? WHERE id=?",
                (release, row["equipment_id"]),
            )
        conn.execute(
            "UPDATE booking_items SET issued_qty=? WHERE id=? AND booking_id=?",
            (qty, item_id, booking_id),
        )
    conn.execute(
        "UPDATE bookings SET status='issued', updated_at=? WHERE id=?",
        (datetime.now().isoformat(), booking_id),
    )
    conn.commit()
    conn.close()

def set_return_data(booking_id: int, returned_by_item: dict):
    conn = connect()
    for item_id, data in returned_by_item.items():
        conn.execute(
            """UPDATE booking_items
               SET returned_qty=?, condition=?, comment=?
               WHERE id=? AND booking_id=?""",
            (data["qty"], data["condition"], data.get("comment"), item_id, booking_id),
        )
    conn.execute(
        "UPDATE bookings SET status='returned', updated_at=? WHERE id=?",
        (datetime.now().isoformat(), booking_id),
    )
    conn.commit()
    conn.close()

def cancel_booking(booking_id: int):
    set_booking_status(booking_id, "canceled")

def change_available_qty(equipment_id: int, delta: int):
    conn = connect()
    conn.execute(
        "UPDATE equipment SET available_qty=MAX(0, available_qty+?) WHERE id=?",
        (delta, equipment_id),
    )
    conn.commit()
    conn.close()

def set_equipment_qty(equipment_id: int, total_qty: int, available_qty: int):
    conn = connect()
    conn.execute(
        "UPDATE equipment SET total_qty=?,available_qty=? WHERE id=?",
        (total_qty, available_qty, equipment_id),
    )
    conn.commit()
    conn.close()

def set_equipment_disabled(equipment_id: int, disabled: bool):
    conn = connect()
    conn.execute(
        "UPDATE equipment SET disabled=? WHERE id=?",
        (1 if disabled else 0, equipment_id),
    )
    conn.commit()
    conn.close()

def get_active_reservation_qty(equipment_id: int, pickup_at: str, return_at: str, exclude_booking_id: int = 0):
    conn = connect()
    row = conn.execute(
        """SELECT COALESCE(SUM(bi.reserved_qty),0) AS qty
           FROM booking_items bi
           JOIN bookings b ON b.id=bi.booking_id
           WHERE bi.equipment_id=?
             AND b.id<>?
             AND b.status IN ('pending','confirmed','issued')
             AND b.pickup_at < ?
             AND b.return_at > ?""",
        (equipment_id, exclude_booking_id, return_at, pickup_at),
    ).fetchone()
    conn.close()
    return int(row["qty"])

def get_available_for_period(equipment_id: int, pickup_at: str, return_at: str, exclude_booking_id: int = 0):
    item = get_equipment_item(equipment_id)
    if not item or item["disabled"]:
        return 0
    # Base stock minus quantities reserved/held by overlapping bookings.
    reserved = get_active_reservation_qty(equipment_id, pickup_at, return_at, exclude_booking_id)
    return max(0, int(item["available_qty"]) - reserved)

def get_due_bookings_for_reminder():
    conn = connect()
    rows = conn.execute(
        """SELECT * FROM bookings
           WHERE status='confirmed'"""
    ).fetchall()
    conn.close()
    return rows
