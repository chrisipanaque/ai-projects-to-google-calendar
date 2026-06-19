import sys
from datetime import datetime, timedelta

from opencode_calendar.config import get_config
from opencode_calendar.time_utils import (
    get_timezone,
    floor_to_half_hour,
    ceil_to_half_hour,
    parse_time_or_datetime,
    resolve_end,
)
from opencode_calendar.db import (
    get_sessions_in_range,
    get_session_count_in_range,
    get_unique_directories,
    get_todos_for_sessions,
    get_user_texts_for_session_ids,
    get_assistant_key_texts,
    get_reasoning_parts,
    get_diffs_for_session_ids,
    get_dep_files_for_session_ids,
    get_tool_call_summary,
    get_tool_call_details,
    get_agent_flow,
    list_recent_sessions,
)
from opencode_calendar.summarizer import generate_block_summary, extract_project_name
from opencode_calendar.calendar_client import (
    _auth as auth_google,
    find_most_recent_block,
    create_block_event,
    update_block_event,
    build_block_description,
    build_placeholder_description,
)


def _fail(msg):
    sys.stderr.write(f"Error: {msg}\n")
    sys.exit(1)


def _check_creds(config):
    if not config["google_credentials_path"]:
        _fail(
            "GOOGLE_CREDENTIALS_PATH not set in .env\n"
            "See README.md for Google Cloud setup instructions."
        )


def _report_session_count(db_path, start_dt, end_dt):
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    n = get_session_count_in_range(db_path, start_ms, end_ms)
    if n:
        print(f"  Sessions in range: {n}")
    else:
        print("  No sessions found in this time range.")
    return n


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


def _extract_session_ids(sessions):
    return [s["id"] for s in sessions]


# ── add command ─────────────────────────────────────────────

def cmd_add(args):
    config = get_config()
    _check_creds(config)
    tz = get_timezone(config)

    now = datetime.now(tz)
    if args.start:
        start_dt = floor_to_half_hour(parse_time_or_datetime(args.start, tz))
    else:
        start_dt = floor_to_half_hour(now)
    end_dt = floor_to_half_hour(start_dt + timedelta(minutes=30))

    tz_name = str(tz)
    description = build_placeholder_description(tz_name)

    print(f"Creating placeholder event:")
    print(f"  Start: {_fmt(start_dt)}")
    print(f"  End:   {_fmt(end_dt)}")

    service = auth_google(config["google_credentials_path"], config["google_token_path"])

    existing = find_most_recent_block(service)
    if existing:
        print(f"  A work block already exists: {existing.get('htmlLink')}")
        existing_start = existing["start"].get("dateTime", "")
        print(f"  Start: {existing_start}")
        ans = input("  Create another one? [y/N]: ").strip().lower()
        if ans != "y":
            print("  Cancelled.")
            return

    event = create_block_event(service, start_dt, end_dt, description, tz_name)
    print(f"\nEvent created: {event.get('htmlLink')}")


# ── end-session command ─────────────────────────────────────

def cmd_end_session(args):
    config = get_config()
    _check_creds(config)
    tz = get_timezone(config)
    db_path = config["db_path"]
    now = datetime.now(tz)

    service = auth_google(config["google_credentials_path"], config["google_token_path"])

    # ── resolve time range ──────────────────────────────────
    if args.start and args.end:
        start_dt = floor_to_half_hour(parse_time_or_datetime(args.start, tz))
        end_dt = ceil_to_half_hour(resolve_end(start_dt, args.end, tz))
        existing_event = None
        mode = "explicit"
        print(f"Explicit time range: {_fmt(start_dt)} → {_fmt(end_dt)}")
    else:
        existing_event = find_most_recent_block(service)
        if existing_event:
            start_str = existing_event["start"].get("dateTime", "")
            try:
                start_dt = datetime.fromisoformat(start_str).astimezone(tz)
            except ValueError:
                _fail(f"Could not parse existing event start: {start_str}")
            end_dt = ceil_to_half_hour(now)
            mode = "from-add"
            print(f"Updating block from {_fmt(start_dt)} → {_fmt(end_dt)}")
        else:
            start_dt = floor_to_half_hour(now - timedelta(hours=1))
            end_dt = ceil_to_half_hour(now)
            mode = "auto"
            print(f"No prior block found — creating from {_fmt(start_dt)} → {_fmt(end_dt)}")

    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(hours=1)

    # ── query sessions in range ─────────────────────────────
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    sessions = get_sessions_in_range(db_path, start_ms, end_ms)
    print(f"  Sessions found: {len(sessions)}")

    if not sessions:
        print("  Creating event with no session data (empty block).")
        tz_name = str(tz)
        description = build_placeholder_description(tz_name)
        if existing_event:
            event = update_block_event(
                service, existing_event["id"], end_dt, description, tz_name,
                title="OpenCode: No sessions",
            )
            print(f"\nEvent updated: {event.get('htmlLink')}")
        else:
            event = create_block_event(service, start_dt, end_dt, description, tz_name)
            print(f"\nEvent created: {event.get('htmlLink')}")
        return

    session_ids = _extract_session_ids(sessions)
    dirs = get_unique_directories(db_path, session_ids)

    print("  Gathering session data...")
    todos = get_todos_for_sessions(db_path, session_ids)
    user_texts = get_user_texts_for_session_ids(db_path, session_ids)
    assistant_texts = get_assistant_key_texts(db_path, session_ids)
    reasoning_parts = get_reasoning_parts(db_path, session_ids)
    diffs = get_diffs_for_session_ids(db_path, session_ids)
    dep_files = get_dep_files_for_session_ids(db_path, session_ids)
    tool_summary = get_tool_call_summary(db_path, session_ids)
    tool_details = get_tool_call_details(db_path, session_ids)
    agent_flow = get_agent_flow(db_path, session_ids)

    print(f"  Todos: {len(todos)} | User msgs: {len(user_texts)} | Files: {len(diffs)}")
    if tool_summary:
        print(f"  Tool calls: {sum(tool_summary.values())} ({len(tool_summary)} types)")

    print("  Generating AI summary...")
    summary, git_context = generate_block_summary(
        sessions, todos, user_texts, assistant_texts,
        reasoning_parts, diffs, dep_files,
        tool_summary, tool_details, agent_flow,
        git_context=None,
        dirs=dirs,
        config=config,
    )
    print("  Summary generated.")

    tz_name = str(tz)
    description = build_block_description(
        summary, git_context, sessions, diffs, tool_summary, tz_name,
    )

    # Build event title
    if len(sessions) == 1:
        title = f"OpenCode: {sessions[0]['title']}"
    else:
        project = None
        for d in dirs:
            project = extract_project_name(d)
            if project:
                break
        date_str = start_dt.strftime("%b %d")
        title = f"OpenCode: {len(sessions)} sessions · {project or date_str}"

    if existing_event:
        print("  Updating existing event...")
        event = update_block_event(
            service, existing_event["id"], end_dt, description, tz_name, title=title,
        )
        print(f"\nEvent updated: {event.get('htmlLink')}")
    else:
        print("  Creating new event...")
        event = create_block_event(service, start_dt, end_dt, description, tz_name, title=title)
        print(f"\nEvent created: {event.get('htmlLink')}")

    if git_context.get("remote_url"):
        print(f"  Repo: {git_context['remote_url']}")


# ── info command (kept for debugging) ───────────────────────

def cmd_info(args):
    config = get_config()
    tz = get_timezone(config)
    db_path = config["db_path"]

    from opencode_calendar.db import get_session
    session = get_session(db_path, args.session_id)
    if not session:
        _fail("No sessions found.")

    print(f"ID:        {session['id']}")
    print(f"Title:     {session['title']}")
    print(f"Agent:     {session['agent']}")
    print(f"Directory: {session['directory']}")
    print(f"Created:   {datetime.fromtimestamp(session['time_created']/1000, tz)}")
    print(f"Updated:   {datetime.fromtimestamp(session['time_updated']/1000, tz)}")
    print(f"Tokens:    {session['tokens_input']:,} in / {session['tokens_output']:,} out")
    print(f"Files:     +{session['summary_additions']}/-{session['summary_deletions']} ({session['summary_files']} files)")


# ── main ────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        prog="opencode-calendar",
        description="Log OpenCode AI coding sessions to Google Calendar",
    )
    parser.add_argument("--db-path", help="Path to opencode.db (default: from .env)")

    sub = parser.add_subparsers(dest="command", required=True)

    # add
    add_p = sub.add_parser("add", help="Create a placeholder calendar block")
    add_p.add_argument("--start", help="Block start time (HH:MM or YYYY-MM-DD HH:MM)")

    # end-session
    end_p = sub.add_parser("end-session", help="Finalize a work block with AI summary")
    end_p.add_argument("--start", help="Block start time (HH:MM or YYYY-MM-DD HH:MM)")
    end_p.add_argument("--end", help="Block end time (HH:MM or YYYY-MM-DD HH:MM)")

    # info
    info_p = sub.add_parser("info", help="Show session details (debug)")
    info_p.add_argument("session_id", nargs="?", help="Session ID (default: most recent)")

    args = parser.parse_args()

    if args.db_path:
        import os
        os.environ["OPENCODE_DB_PATH"] = args.db_path

    if args.command == "add":
        cmd_add(args)
    elif args.command == "end-session":
        cmd_end_session(args)
    elif args.command == "info":
        cmd_info(args)
