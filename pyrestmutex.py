from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3
import time
import os
import asyncio
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from queue import Queue, Empty
from threading import Thread

DB_PATH = os.getenv("DB_PATH", "locks.db")
MAX_LOG_ENTRIES = 1000

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

log_queue = Queue()


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS locks (
                name TEXT PRIMARY KEY,
                owner TEXT,
                expires_at INTEGER
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS lock_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER,
                name TEXT,
                owner TEXT,
                action TEXT
            )
        ''')
        conn.commit()


def enqueue_log(name: str, owner: str, action: str):
    log_queue.put((int(time.time()), name, owner, action))


def log_worker():
    while True:
        try:
            ts, name, owner, action = log_queue.get(timeout=1)
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO lock_events (timestamp, name, owner, action) VALUES (?, ?, ?, ?)",
                    (ts, name, owner, action)
                )
                count = conn.execute(
                    "SELECT COUNT(*) FROM lock_events").fetchone()[0]
                if count > MAX_LOG_ENTRIES:
                    to_delete = count - MAX_LOG_ENTRIES
                    conn.execute("""
                        DELETE FROM lock_events
                        WHERE id IN (
                            SELECT id FROM lock_events
                            ORDER BY timestamp ASC
                            LIMIT ?
                        )
                    """, (to_delete,))
                conn.commit()
        except Empty:
            continue


def cleanup_expired(conn):
    now = int(time.time())
    expired = conn.execute(
        "SELECT name, owner FROM locks WHERE expires_at <= ?", (now,)).fetchall()
    for name, owner in expired:
        enqueue_log(name, owner, "expired")
    conn.execute("DELETE FROM locks WHERE expires_at <= ?", (now,))
    conn.commit()


@app.on_event("startup")
async def startup():
    init_db()
    Thread(target=log_worker, daemon=True).start()
    asyncio.create_task(cleanup_worker())


async def cleanup_worker():
    while True:
        with get_connection() as conn:
            cleanup_expired(conn)
        await asyncio.sleep(10)


class LockRequest(BaseModel):
    owner: str
    ttl: int = 30


class RenewRequest(BaseModel):
    owner: str
    ttl: int = 30


@app.post("/lock/{name}")
def acquire_lock(name: str, request: LockRequest):
    now = int(time.time())
    expires_at = now + request.ttl
    with get_connection() as conn:
        cleanup_expired(conn)

        cursor = conn.execute("""
            INSERT INTO locks (name, owner, expires_at)
            SELECT ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM locks WHERE name = ?
            )
        """, (name, request.owner, expires_at, name))

        conn.commit()

        if cursor.rowcount == 1:
            enqueue_log(name, request.owner, "acquire")
            return {"status": "locked"}
        else:
            row = conn.execute(
                "SELECT owner, expires_at FROM locks WHERE name = ?", (name,)
            ).fetchone()
            enqueue_log(name, request.owner, f"already_locked by {row[0]}")
            return {"status": "already_locked", "owner": row[0], "expires_at": row[1]}


@app.post("/unlock/{name}")
def release_lock(name: str, request: LockRequest):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT owner FROM locks WHERE name = ?", (name,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Lock not found")
        if row[0] != request.owner:
            raise HTTPException(
                status_code=403, detail="You don't own the lock")
        conn.execute("DELETE FROM locks WHERE name = ?", (name,))
        conn.commit()
        enqueue_log(name, request.owner, "release")
        return {"status": "unlocked"}


@app.post("/renew/{name}")
def renew_lock(name: str, request: RenewRequest):
    new_expires_at = int(time.time()) + request.ttl
    with get_connection() as conn:
        row = conn.execute(
            "SELECT owner FROM locks WHERE name = ?", (name,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Lock not found")
        if row[0] != request.owner:
            raise HTTPException(
                status_code=403, detail="You don't own the lock")
        conn.execute("UPDATE locks SET expires_at = ? WHERE name = ?",
                     (new_expires_at, name))
        conn.commit()
        enqueue_log(name, request.owner, "renew")
        return {"status": "renewed", "new_expires_at": new_expires_at}


@app.get("/status/{name}")
def lock_status(name: str):
    with get_connection() as conn:
        cleanup_expired(conn)
        row = conn.execute(
            "SELECT owner, expires_at FROM locks WHERE name = ?", (name,)).fetchone()
        if not row:
            return {"status": "free"}
        return {"status": "locked", "owner": row[0], "expires_at": row[1]}


@app.get("/locks")
def list_locks():
    now = int(time.time())
    with get_connection() as conn:
        cleanup_expired(conn)
        cursor = conn.execute(
            "SELECT name, owner, expires_at FROM locks ORDER BY name")
        return [{"name": name, "owner": owner, "expires_at": expires_at, "ttl_left": expires_at - now}
                for name, owner, expires_at in cursor]


@app.get("/log")
def get_log():
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT timestamp, name, owner, action
            FROM lock_events
            ORDER BY timestamp DESC
            LIMIT 100
        """)
        return [{"timestamp": ts, "name": name, "owner": owner, "action": action}
                for ts, name, owner, action in cursor]


@app.get("/", response_class=FileResponse)
def ui():
    return "static/index.html"
