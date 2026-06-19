import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
CALENDAR_MARKER = "<!-- opencode-calendar -->"


def _auth(credentials_path, token_path):
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"Google credentials not found at {credentials_path}\n"
                    "Download credentials.json from\n"
                    "https://console.cloud.google.com/apis/credentials"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, SCOPES
            )
            creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(token_path) or ".", exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def find_most_recent_block(service):
    try:
        events = (
            service.events()
            .list(
                calendarId="primary",
                q="opencode-calendar",
                maxResults=10,
                orderBy="startTime",
                singleEvents=True,
            )
            .execute()
        )
        items = events.get("items", [])
        for item in reversed(items):
            desc = item.get("description", "")
            if CALENDAR_MARKER in desc:
                return item
        return None
    except HttpError:
        return None


def find_block_by_id(service, event_id):
    try:
        return service.events().get(calendarId="primary", eventId=event_id).execute()
    except HttpError:
        return None


def create_block_event(service, start_dt, end_dt, description, tz, title=None):
    if not title:
        title = "AI Project: In progress..."
    event = {
        "summary": title,
        "description": description,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": str(tz),
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": str(tz),
        },
    }
    try:
        created = (
            service.events()
            .insert(calendarId="primary", body=event)
            .execute()
        )
        return created
    except HttpError as e:
        raise RuntimeError(f"Failed to create calendar event: {e}")


def update_block_event(service, event_id, end_dt, description, tz, title=None):
    try:
        event = service.events().get(calendarId="primary", eventId=event_id).execute()
    except HttpError as e:
        raise RuntimeError(f"Failed to find event to update: {e}")

    event["end"] = {
        "dateTime": end_dt.isoformat(),
        "timeZone": str(tz),
    }
    if description:
        event["description"] = description
    if title:
        event["summary"] = title

    try:
        updated = (
            service.events()
            .update(calendarId="primary", eventId=event_id, body=event)
            .execute()
        )
        return updated
    except HttpError as e:
        raise RuntimeError(f"Failed to update calendar event: {e}")


def build_block_description(summary_text, git_context, sessions, diffs, tool_summary, tz_name):
    parts = []

    parts.append(summary_text)
    parts.append("")

    parts.append("---")
    parts.append("")

    if git_context.get("remote_url"):
        parts.append(f"Repository: {git_context['remote_url']}")
    if git_context.get("branch"):
        parts.append(f"Branch: {git_context['branch']}")
    if git_context.get("commits"):
        parts.append("Recent Commits:")
        for c in git_context["commits"]:
            parts.append(f"  • {c}")
    parts.append("")

    total_duration = 0
    total_tokens_in = 0
    total_tokens_out = 0
    for s in sessions:
        total_duration += (s["time_updated"] - s["time_created"])
        total_tokens_in += s["tokens_input"]
        total_tokens_out += s["tokens_output"]

    duration_min = round(total_duration / 60000.0, 1)
    agents = sorted(set(s["agent"] for s in sessions))

    total_add = sum(d.get("additions", 0) or 0 for d in (diffs or []))
    total_del = sum(d.get("deletions", 0) or 0 for d in (diffs or []))
    total_files = len(diffs) if diffs else 0

    parts.append(f"Duration: {duration_min} min | Sessions: {len(sessions)} | Agents: {', '.join(agents)}")
    parts.append(f"Files: +{total_add}/-{total_del} across {total_files} files")
    parts.append(f"Tokens: {total_tokens_in:,} in / {total_tokens_out:,} out")

    if diffs:
        parts.append("")
        parts.append("Files Modified:")
        for d in diffs[:15]:
            icon = {"added": "+", "modified": "~", "deleted": "-"}.get(d["status"], "*")
            parts.append(f"  {icon} `{d['file']}`")
        if len(diffs) > 15:
            parts.append(f"  … and {len(diffs) - 15} more")

    if tool_summary:
        parts.append("")
        parts.append("AI Tool Activity:")
        for name, count in list(tool_summary.items())[:8]:
            parts.append(f"  • {name}: {count}")

    parts.append("")
    parts.append(CALENDAR_MARKER)
    parts.append(f"Timezone: {tz_name}")

    return "\n".join(parts)


def build_placeholder_description(tz_name):
    parts = [
        "OpenCode work block — in progress.",
        "",
        "Run `opencode-calendar end-session` to finalize this block.",
        "",
        CALENDAR_MARKER,
        f"Timezone: {tz_name}",
    ]
    return "\n".join(parts)
