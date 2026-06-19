import sqlite3
import json
import os
from collections import Counter
from typing import Optional

BUILD_ARTIFACT_PREFIXES = (
    "target/", "build/", "dist/", "node_modules/",
    ".git/", "__pycache__/", ".next/", ".venv/",
    "vendor/", "third_party/",
)

DEPENDENCY_FILES = {
    "package.json", "pom.xml", "Cargo.toml", "pyproject.toml",
    "requirements.txt", "Gemfile", "go.mod", "build.gradle",
    "build.gradle.kts", "composer.json",
}


def _connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ── Session queries ──────────────────────────────────────────

def get_session(db_path: str, session_id: Optional[str] = None):
    conn = _connect(db_path)
    cur = conn.cursor()
    if session_id:
        cur.execute("SELECT * FROM session WHERE id = ?", (session_id,))
    else:
        cur.execute("SELECT * FROM session ORDER BY time_created DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_sessions_in_range(db_path: str, start_ms: int, end_ms: int):
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """SELECT * FROM session
           WHERE time_created >= ? AND time_created <= ?
           ORDER BY time_created""",
        (start_ms, end_ms),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_count_in_range(db_path: str, start_ms: int, end_ms: int):
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM session WHERE time_created >= ? AND time_created <= ?",
        (start_ms, end_ms),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_unique_directories(db_path: str, session_ids: list):
    if not session_ids:
        return []
    placeholders = ",".join("?" for _ in session_ids)
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        f"SELECT DISTINCT directory FROM session WHERE id IN ({placeholders}) AND directory IS NOT NULL AND directory != ''",
        session_ids,
    )
    rows = cur.fetchall()
    conn.close()
    return [r["directory"] for r in rows]


# ── Todo queries ────────────────────────────────────────────

def get_todos_for_sessions(db_path: str, session_ids: list):
    if not session_ids:
        return []
    placeholders = ",".join("?" for _ in session_ids)
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        f"SELECT session_id, content, status, priority, position FROM todo WHERE session_id IN ({placeholders}) ORDER BY session_id, position",
        session_ids,
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Text / conversation queries ─────────────────────────────

def get_user_texts_for_session_ids(db_path: str, session_ids: list):
    if not session_ids:
        return []
    placeholders = ",".join("?" for _ in session_ids)
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        f"""SELECT p.session_id, p.time_created, p.data FROM part p
            JOIN message m ON p.message_id = m.id
            WHERE p.session_id IN ({placeholders})
              AND json_extract(p.data, '$.type') = 'text'
              AND json_extract(p.data, '$.text') IS NOT NULL
              AND json_extract(m.data, '$.role') = 'user'
            ORDER BY p.time_created""",
        session_ids,
    )
    rows = cur.fetchall()
    conn.close()

    results = []
    for r in rows:
        try:
            data = json.loads(r["data"])
            text = (data.get("text") or "").strip()
            if text:
                results.append({
                    "session_id": r["session_id"],
                    "time_created": r["time_created"],
                    "text": text,
                })
        except json.JSONDecodeError:
            continue
    return results


def get_assistant_key_texts(db_path: str, session_ids: list):
    if not session_ids:
        return []
    placeholders = ",".join("?" for _ in session_ids)
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        f"""SELECT p.session_id, p.time_created, p.data FROM part p
            JOIN message m ON p.message_id = m.id
            WHERE p.session_id IN ({placeholders})
              AND json_extract(p.data, '$.type') = 'text'
              AND json_extract(p.data, '$.text') IS NOT NULL
              AND json_extract(m.data, '$.role') = 'assistant'
              AND length(json_extract(p.data, '$.text')) > 100
            ORDER BY p.time_created""",
        session_ids,
    )
    rows = cur.fetchall()
    conn.close()

    results = []
    for r in rows:
        try:
            data = json.loads(r["data"])
            text = (data.get("text") or "").strip()
            if text:
                results.append({
                    "session_id": r["session_id"],
                    "time_created": r["time_created"],
                    "text": text,
                })
        except json.JSONDecodeError:
            continue
    return results


def get_reasoning_parts(db_path: str, session_ids: list):
    if not session_ids:
        return []
    placeholders = ",".join("?" for _ in session_ids)
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        f"""SELECT session_id, data FROM part
            WHERE session_id IN ({placeholders})
              AND json_extract(data, '$.type') = 'reasoning'
              AND json_extract(data, '$.text') IS NOT NULL
            ORDER BY time_created""",
        session_ids,
    )
    rows = cur.fetchall()
    conn.close()

    results = []
    for r in rows:
        try:
            data = json.loads(r["data"])
            text = (data.get("text") or "").strip()
            if text:
                results.append({
                    "session_id": r["session_id"],
                    "text": text,
                })
        except json.JSONDecodeError:
            continue
    return results


# ── Diff queries ────────────────────────────────────────────

def get_diffs_for_session_ids(db_path: str, session_ids: list):
    if not session_ids:
        return []
    placeholders = ",".join("?" for _ in session_ids)
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        f"""SELECT json_extract(d.value, '$.file') as file,
                  json_extract(d.value, '$.additions') as additions,
                  json_extract(d.value, '$.deletions') as deletions,
                  json_extract(d.value, '$.status') as status
           FROM message m, json_each(json_extract(m.data, '$.summary.diffs')) d
           WHERE m.session_id IN ({placeholders})
             AND json_extract(m.data, '$.role') = 'user'""",
        session_ids,
    )
    rows = cur.fetchall()
    conn.close()

    seen = set()
    diffs = []
    for row in rows:
        file = row["file"]
        if not file or file.startswith(BUILD_ARTIFACT_PREFIXES):
            continue
        if file not in seen:
            seen.add(file)
            diffs.append({
                "file": file,
                "additions": int(row["additions"] or 0),
                "deletions": int(row["deletions"] or 0),
                "status": row["status"] or "modified",
            })
    return diffs


def get_dep_files_for_session_ids(db_path: str, session_ids: list):
    if not session_ids:
        return []
    placeholders = ",".join("?" for _ in session_ids)
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        f"""SELECT DISTINCT json_extract(d.value, '$.file') as file
           FROM message m, json_each(json_extract(m.data, '$.summary.diffs')) d
           WHERE m.session_id IN ({placeholders})
             AND json_extract(m.data, '$.role') = 'user'""",
        session_ids,
    )
    rows = cur.fetchall()
    conn.close()

    deps = []
    for r in rows:
        file = r["file"] or ""
        if os.path.basename(file) in DEPENDENCY_FILES:
            deps.append(file)
    return deps


# ── Tool call queries ───────────────────────────────────────

def get_tool_call_summary(db_path: str, session_ids: list):
    if not session_ids:
        return {}
    placeholders = ",".join("?" for _ in session_ids)
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        f"""SELECT json_extract(data, '$.tool') as tool_name,
                  json_extract(data, '$.state.status') as status
           FROM part
           WHERE session_id IN ({placeholders})
             AND json_extract(data, '$.type') = 'tool'""",
        session_ids,
    )
    rows = cur.fetchall()
    conn.close()

    tool_counter = Counter()
    for r in rows:
        name = r["tool_name"]
        if name:
            tool_counter[name] += 1
    return dict(tool_counter.most_common())


def get_tool_call_details(db_path: str, session_ids: list, limit_per_type=3):
    if not session_ids:
        return []
    placeholders = ",".join("?" for _ in session_ids)
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        f"""SELECT json_extract(data, '$.tool') as tool_name,
                  json_extract(data, '$.state.input.filePath') as file,
                  json_extract(data, '$.state.input.command') as cmd
           FROM part
           WHERE session_id IN ({placeholders})
             AND json_extract(data, '$.type') = 'tool'
           ORDER BY time_created""",
        session_ids,
    )
    rows = cur.fetchall()
    conn.close()

    reads = []
    commands = []
    for r in rows:
        name = r["tool_name"]
        if name == "read" and r["file"]:
            reads.append(r["file"])
        elif name == "bash" and r["cmd"]:
            commands.append(r["cmd"])

    return {
        "reads": reads[:limit_per_type],
        "commands": commands[:limit_per_type],
    }


# ── Agent flow query ────────────────────────────────────────

def get_agent_flow(db_path: str, session_ids: list):
    if not session_ids:
        return []
    placeholders = ",".join("?" for _ in session_ids)
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        f"""SELECT session_id, type, seq, time_created, data
           FROM session_message
           WHERE session_id IN ({placeholders})
             AND type = 'agent-switched'
           ORDER BY time_created""",
        session_ids,
    )
    rows = cur.fetchall()
    conn.close()

    agents = []
    for r in rows:
        try:
            d = json.loads(r["data"])
            agent = d.get("agent")
            if agent:
                agents.append(agent)
        except json.JSONDecodeError:
            continue
    return agents


# ── Utility ─────────────────────────────────────────────────

def list_recent_sessions(db_path: str, limit=5):
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, agent, time_created, time_updated FROM session ORDER BY time_created DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
