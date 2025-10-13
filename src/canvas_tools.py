"""
Canvas tools module: Canvas API helpers, tool functions, JSON schemas, and a dispatcher.
"""

from __future__ import annotations

import os
import json
import re
import html
import hashlib
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

import requests
from dateutil import parser as dateparser
from dotenv import load_dotenv

load_dotenv()

CANVAS_BASE_URL = os.environ["CANVAS_BASE_URL"].rstrip("/")
CANVAS_TOKEN = os.environ["CANVAS_TOKEN"]
DAYS_AHEAD_DEFAULT = int(os.getenv("DAYS_AHEAD_DEFAULT"))

SESSION = requests.Session()
SESSION.headers.update({"Authorization": f"Bearer {CANVAS_TOKEN}"})
STATE_FILE = "created_blocks_canvas.json"


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat()}] {msg}", flush=True)


def canvas_get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{CANVAS_BASE_URL}{path}"
    log(f"GET {url} | params={params}")
    t0 = time.time()
    r = SESSION.get(url, params=params or {}, timeout=30)
    r.raise_for_status()
    log(f"✔ GET {url} ({time.time() - t0:.2f}s)")
    return r.json()


def canvas_post(path: str, payload: Dict[str, Any]) -> Any:
    url = f"{CANVAS_BASE_URL}{path}"
    preview = json.dumps(payload)[:200]
    log(f"POST {url} | payload={preview}...")
    t0 = time.time()
    r = SESSION.post(url, json=payload, timeout=30)
    r.raise_for_status()
    log(f"✔ POST {url} ({time.time() - t0:.2f}s)")
    return r.json()


def strip_html(s: Optional[str]) -> str:
    if not s:
        return ""
    s = re.sub(r"<(script|style).*?</\\1>", "", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _load_seen() -> Set[str]:
    try:
        with open(STATE_FILE, "r") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_seen(seen: Set[str]) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(list(seen)), f, indent=2)


def _hash_block(title: str, start_iso: str, end_iso: str) -> str:
    return hashlib.sha1(f"{title}|{start_iso}|{end_iso}".encode()).hexdigest()


def _get_user_id() -> int:
    me = canvas_get("/api/v1/users/self")
    return int(me["id"])


def get_upcoming_assignments(days_ahead: int = DAYS_AHEAD_DEFAULT) -> str:
    """Return a JSON string: {"assignments": [...]} with cleaned fields.

    Each item contains: course_name, name, due_at (ISO), points_possible,
    submission_types, html_url, summary_line.
    """
    log(f"→ get_upcoming_assignments(days_ahead={days_ahead})")
    horizon = datetime.now(timezone.utc) + timedelta(days=int(days_ahead))

    courses = canvas_get(
        "/api/v1/courses", params={"enrollment_state": "active", "per_page": 100}
    )

    out: List[Dict[str, Any]] = []
    for c in courses or []:
        cid = c.get("id")
        cname = c.get("name") or f"Course {cid}"
        if not cid:
            continue
        items = canvas_get(
            f"/api/v1/courses/{cid}/assignments",
            params={"bucket": "upcoming", "per_page": 100},
        )
        for a in items or []:
            due_at = a.get("due_at")
            if not due_at:
                continue
            try:
                due = dateparser.parse(due_at)
            except Exception:
                continue
            if due <= horizon:
                points = a.get("points_possible")
                subs = a.get("submission_types", [])
                summary_line = f"**{cname}** — {a.get('name')} — Due: {due.isoformat()}"
                out.append(
                    {
                        "course_name": cname,
                        "name": a.get("name"),
                        "due_at": due.isoformat(),
                        "points_possible": points,
                        "submission_types": subs,
                        "html_url": a.get("html_url"),
                        "summary_line": summary_line,
                        "course_id": cid,
                        "assignment_id": a.get("id"),
                    }
                )

    out.sort(key=lambda x: x.get("due_at") or "")
    log(f"← Found {len(out)} upcoming assignments")
    return json.dumps({"assignments": out})


def get_submission_status(course_id: int, assignment_id: int) -> str:
    log(
        f"→ get_submission_status(course_id={course_id}, assignment_id={assignment_id})"
    )
    sub = canvas_get(
        f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/self"
    )
    status = {
        "late": sub.get("late"),
        "missing": sub.get("missing"),
        "submitted_at": sub.get("submitted_at"),
        "graded_at": sub.get("graded_at"),
        "workflow_state": sub.get("workflow_state"),
        "score": sub.get("score"),
    }
    log(f"← Submission status: {status}")
    return json.dumps(status)


def create_canvas_event(title: str, start_at: str, end_at: str) -> str:
    """Create ONE event on the user's default Canvas calendar.

    Args must be ISO 8601 strings with timezone offsets. Returns a JSON string
    of shape: {"created": [{id, title, start_at, end_at}], "count": 1}
    """
    log("→ create_canvas_event (single)")

    def _to_iso8601_z(s: str) -> str:
        return s.replace("+00:00", "Z") if isinstance(s, str) else s

    if not (title and start_at and end_at):
        raise ValueError("title, start_at, and end_at are required")

    start_at = _to_iso8601_z(start_at)
    end_at = _to_iso8601_z(end_at)

    user_id = _get_user_id()
    context_code = f"user_{user_id}"

    seen = _load_seen()
    h = _hash_block(title, start_at, end_at)
    if h in seen:
        log(f"↷ Skipping duplicate event: {title}")
        return json.dumps({"created": [], "count": 0, "skipped": True})

    payload = {
        "calendar_event": {
            "context_code": context_code,
            "title": title,
            "start_at": start_at,
            "end_at": end_at,
            "description": "",
            "location_name": "Study",
        }
    }

    res = canvas_post("/api/v1/calendar_events", payload)
    seen.add(h)
    _save_seen(seen)

    out = {"id": res.get("id"), "title": title, "start_at": start_at, "end_at": end_at}
    log("← Created 1 event")
    return json.dumps({"created": [out], "count": 1})


def execute_function(name: str, args: Dict[str, Any]) -> str:
    if name == "get_upcoming_assignments":
        return get_upcoming_assignments(**args)
    if name == "get_submission_status":
        return get_submission_status(**args)
    if name == "create_canvas_event":
        return create_canvas_event(**args)
    return json.dumps({"error": f"Unknown tool {name}"})


TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_assignments",
            "description": "List upcoming assignments for the next N days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "How many days ahead to look.",
                        "minimum": 1,
                        "maximum": 60,
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_submission_status",
            "description": "Get the current user's submission status for a specific assignment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "integer"},
                    "assignment_id": {"type": "integer"},
                },
                "required": ["course_id", "assignment_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_canvas_event",
            "description": "Create ONE study event on the Canvas calendar. Requires title, start_at, end_at (ISO 8601 with timezone).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title"},
                    "start_at": {
                        "type": "string",
                        "description": "Start time (ISO 8601, e.g. 2025-10-12T15:00:00-07:00)",
                    },
                    "end_at": {
                        "type": "string",
                        "description": "End time (ISO 8601, e.g. 2025-10-12T17:00:00-07:00)",
                    },
                },
                "required": ["title", "start_at", "end_at"],
                "additionalProperties": False,
            },
        },
    },
]
