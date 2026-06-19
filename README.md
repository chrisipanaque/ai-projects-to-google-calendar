# opencode-calendar

**A portfolio builder for AI engineers.** Every OpenCode coding session is logged to Google Calendar with an AI-generated technical summary focused on architecture patterns, design decisions, and enterprise considerations.

When a recruiter, ATS system, or LLM agent scans your calendar, they see concrete evidence of AI engineering experience — not just "worked on project X." Each event contains the full technical narrative: what problem was solved, which patterns were used, what files were changed, and how the system evolved.

```
┌──────────────┐     ┌──────────────┐     ┌─────────────────┐
│  opencode.db  │ ──▶ │  opencode-   │ ──▶ │  Google Calendar │
│  (SQLite)     │     │  calendar    │     │  (primary)      │
└──────────────┘     └──────────────┘     └─────────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  GitHub      │
                    │  Models API  │
                    │  (free tier) │
                    └──────────────┘
```

---

## Data Sources

Every calendar event's AI summary is built from these 11 sources. You don't need to do anything special — the tool reads them automatically from the OpenCode database and your local git repos.

| # | Source | What It Reveals | Example Output |
|---|---|---|---|
| 1 | **Session titles** | What each session was about | "Implement Redis write-through cache" |
| 2 | **User prompts** | The problem, requirements, constraints you described | "sub-50ms latency, write-through pattern, fallback to PG" |
| 3 | **AI reasoning** | Design decisions the AI made | "Chose lettuce-core over jedis for async support" |
| 4 | **File diffs** | Every source file created or modified (build artifacts excluded) | "14 files: +src/cache/RedisCache.java (+93)" |
| 5 | **Dependency files** | Libraries and versions introduced | "pom.xml: +lettuce-core 6.3.0" |
| 6 | **Todo items** | Tasks planned vs completed | "8/8 tasks completed ✓" |
| 7 | **Tool calls** | How the AI worked — reads, writes, bash commands, grep, glob | "105 bash, 37 write, 36 read, 12 grep" |
| 8 | **Agent flow** | Workflow phases: plan → build → explore → plan | "plan→build→build→plan (4 agent switches)" |
| 9 | **Git context** | Branch name, remote URL, recent commits | "feat/redis-cache · user/project · a1b2c3d" |
| 10 | **Project directories** | Which projects were touched | "redis-cache, docs-site" |
| 11 | **Duration & tokens** | How long and how much AI compute | "34 min · 12K tokens · agent: build" |

All 11 sources are fed into the LLM (GitHub Models, free tier) which synthesizes a technical summary covering architecture patterns, design decisions, specific libraries, and data flow.

---

## Quick Start

```bash
# 1. Install
pip install .

# 2. Set up configuration
cp .env.example .env
# then edit .env (see Setup section below)

# 3. Verify database connection
opencode-calendar info

# 4. Start a work block
opencode-calendar add --start "06:00"

# 5. Finalize when done
opencode-calendar end-session --start "06:00" --end "09:00"
```

---

## Command Reference

| Command | What It Does |
|---|---|
| `opencode-calendar add` | Creates a placeholder event at `floor(now)` (rounded down to nearest half-hour) |
| `opencode-calendar add --start "06:00"` | Creates a placeholder at 6:00 AM today |
| `opencode-calendar end-session` | Auto-detects the block: if an `add` placeholder exists, uses its start time; otherwise uses the last 1 hour |
| `opencode-calendar end-session --start "06:00" --end "09:00"` | Explicit 3-hour block starting at 6:00 AM |
| `opencode-calendar end-session --start "2026-06-19 22:00" --end "2026-06-20 03:00"` | Overnight session (past midnight) |
| `opencode-calendar info` | Debug command: shows the most recent session with all raw data |

**Flags:**

- `--start HH:MM` or `--start "YYYY-MM-DD HH:MM"` — Start time. `HH:MM` assumes today.
- `--end HH:MM` or `--end "YYYY-MM-DD HH:MM"` — End time. If end < start with no date, assumes next day (overnight).
- `--db-path PATH` — Custom OpenCode database path (overrides `.env`).

---

## Scenarios

### Morning work block (normal)
```bash
opencode-calendar add --start "06:00"
# ... work in OpenCode from 6:00 AM to 9:00 AM ...
opencode-calendar end-session --start "06:00" --end "09:00"
```
Aggregates all sessions between 6:00–9:00 AM into one calendar event. Multiple short sessions (2-3 min each) are combined into a single technical summary.

### No placeholder created
```bash
# You forgot to call "add"
opencode-calendar end-session
```
Auto-creates the event from scratch using the last 1 hour of session data. The event spans from `floor(now - 1h)` to `ceil(now)`.

### Overnight work
```bash
opencode-calendar end-session --start "22:00" --end "03:00"
```
Detects that 03:00 < 22:00 and assumes the end time is the next day. The calendar event shows 10:00 PM → 3:00 AM.

### Working in a different timezone
```bash
# .env
TIMEZONE=Europe/London
```
All calendar events use London time. The system timezone is auto-detected if not set, but setting it explicitly ensures correct times when traveling or using a remote machine.

### Catching up on past work
```bash
opencode-calendar end-session --start "2026-06-19 06:00" --end "2026-06-19 09:00"
```
Creates a calendar event for an exact past time period. Useful for backfilling sessions you forgot to log.

### Multiple projects in one block
```bash
# Sessions touched: redis-project/ and docs-site/
opencode-calendar end-session --start "06:00" --end "09:00"
```
All sessions across all directories are merged into one block summary. The title becomes `AI Project: N sessions · project1, project2`.

---

## Setup

### `.env` configuration

```ini
OPENCODE_DB_PATH=~/.local/share/opencode/opencode.db
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_TOKEN_PATH=token.json
GITHUB_TOKEN=ghp_your_token_here
GITHUB_MODEL=gpt-4o-mini
TIMEZONE=America/New_York
```

#### `GOOGLE_CREDENTIALS_PATH`

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or select existing)
3. Search for **Google Calendar API** → **Enable**
4. Go to **APIs & Services → Credentials**
5. Click **Create Credentials → OAuth client ID**
6. Application type: **Desktop app**
7. Name it `opencode-calendar` → **Create**
8. Download the JSON file and save it as `credentials.json` in this directory
9. On first run, a browser will open asking you to authorize the app. The resulting token is saved to `GOOGLE_TOKEN_PATH` (auto-created).

#### `GITHUB_TOKEN`

1. Go to [GitHub Settings → Tokens (classic)](https://github.com/settings/tokens)
2. Click **Generate new token → Generate new token (classic)**
3. Name it `opencode-calendar`
4. **No scopes are needed** — GitHub Models API authenticates by token presence alone
5. Click **Generate token** and copy the value (starts with `ghp_` or `github_pat_`)

This gives you free access to `gpt-4o-mini` via GitHub Models. No credit card required.

#### `TIMEZONE`

IANA timezone name: `America/New_York`, `Europe/London`, `Asia/Tokyo`, `America/Los_Angeles`, etc. If left blank, the tool auto-detects your system timezone. Set it explicitly if you work across timezones or on a remote machine.

#### `OPENCODE_DB_PATH`

Defaults to `~/.local/share/opencode/opencode.db`. Only set this if your OpenCode database is stored elsewhere.

#### `GITHUB_MODEL`

Defaults to `gpt-4o-mini` (free tier). Change to `gpt-4o`, `o1-mini`, or any model available on [GitHub Models](https://github.com/marketplace/models).

---

## Getting the Best Summaries

The quality of your calendar events depends on what the LLM has to work with. Small changes in how you interact with OpenCode produce dramatically better summaries.

### Start sessions with architecture context

| | Prompt | Resulting Summary |
|---|---|---|
| **Okay** | "Add Redis caching to the search endpoint" | "Added Redis caching to search endpoint" |
| **Better** | "We need sub-50ms search latency. Implement Redis caching using the write-through pattern with lettuce-core 6.3.0. Cache miss falls back to PostgreSQL via the existing repository interface." | "Implemented a write-through Redis cache layer for search optimization using lettuce-core 6.3.0. The strategy pattern wraps the repository interface with automatic cache invalidation on writes and PostgreSQL fallback on miss. Average latency reduced from 120ms to sub-50ms." |

**Why:** The LLM extracts requirements, constraints, and patterns from your prompt. A bare instruction produces a bare summary. A rich prompt produces a rich summary.

### Name architecture patterns explicitly

| | Prompt | Resulting Summary |
|---|---|---|
| **Okay** | "Build a queue system" | "Built a queue system" |
| **Better** | "Implement an event streaming platform using the producer-consumer pattern with append-only logs, TCP-based broker, and configurable segment retention. No Kafka — from scratch in Java 21." | "Designed a production-grade event streaming platform implementing the producer-consumer pattern with append-only logs, TCP broker architecture (Netty-based), and configurable segment retention. Built from scratch in Java 21 with zero external dependencies." |

**Why:** Pattern names (producer-consumer, CQRS, event-driven, strategy, observer) are the vocabulary the summary uses. Spell them out in your prompts and the LLM will structure the summary around them.

### Use iterative refinement to add design context

| | Prompt | Resulting Summary |
|---|---|---|
| **Okay** | "go ahead" | (no additional context — summary stays generic) |
| **Better** | "Go ahead with the implementation. Use the strategy pattern for interchangeable backends and dependency injection via constructor parameters." | "Implemented using the strategy pattern with constructor-based dependency injection, allowing interchangeable backends verified in the same session." |

**Why:** Approval messages are the second most common input type. Treat them as opportunities to inject design intent, not just confirmation.

### Close the loop with a summary ask

| | Prompt | Resulting Summary |
|---|---|---|
| **Okay** | "done" | (summary relies entirely on inferred context) |
| **Better** | "Summarize the architecture — what patterns did we use, what files were created, and how does data flow through the system?" | "Architecture summary: write-through caching with strategy pattern. Files: RedisCache.java (+93), CacheStrategy.java (+45), UserRepository.java (~12). Data flow: API → cache (Redis) → fallback DB (PostgreSQL)." |

**Why:** The AI's natural language summary of the session is preserved in the calendar event. Prompt it explicitly and the result is structured, thorough, and portfolio-ready.

### Branch naming tells a story

| | Branch | What the Calendar Shows |
|---|---|---|
| **Okay** | `fix` | Branch: fix |
| **Better** | `feat/redis-write-through-strategy` | Branch: feat/redis-write-through-strategy |

**Why:** Branch names are included verbatim in the calendar event. A descriptive branch name conveys the feature's purpose before the LLM even reads a line of code.

### Commit messages add narrative

| | Commit Message | What the Calendar Shows |
|---|---|---|
| **Okay** | `fix stuff` | a1b2c3d fix stuff |
| **Better** | `feat: add Redis write-through cache with lettuce client` | a1b2c3d feat: add Redis write-through cache with lettuce client |

**Why:** The last 5 commit messages appear in every calendar event. Conventional commits (feat:, fix:, refactor:) format cleanly and convey semantic intent.

### Work from project directories

Git remote URL is automatically captured from `git remote get-url origin`. Working from the project root ensures the correct GitHub link appears in every calendar event. OpenCode projects set the workspace directory automatically — just open your project in OpenCode.

---

## Example Calendar Event

Here is what a finalized event looks like in Google Calendar:

```
Title: AI Project: 12 sessions · agentic-code-review-tool

Description:

## Summary
Built an AI-powered code review tool that uses the agentic pattern to
iteratively analyze pull requests. The system implements a multi-agent
architecture where a coordinator agent delegates files to specialized
reviewer agents (security, performance, style), each running gpt-4o-mini
in parallel. Results are aggregated into a structured report with severity
levels and line-level annotations.

Key architecture decisions:
- Agentic pattern with coordinator + specialized reviewer agents
- Parallel execution model with bounded thread pool (4 workers)
- Structured output format (JSON schema) instead of free-text parsing
- Stateless agents — all state managed by coordinator
- Review history persisted to SQLite for trend analysis

## Technical Details
- **Agent flow:** plan→build→plan→build→build (5 switches)
- **Tool activity:** 42 reads, 28 writes, 15 bash, 8 grep
- **Dependencies:** google-generativeai 0.8.0, pydantic 2.7.0
- **Tokens consumed:** 28,450 total across 12 sessions

## Project Context
- **Repository:** git@github.com:user/agentic-code-review.git
- **Branch:** feat/parallel-review-agents
- **Recent Commits:**
  • 2a3b4c5d feat: add parallel agent coordinator with thread pool
  • 6e7f8g9h feat: implement security reviewer agent
  • 0a1b2c3d feat: implement performance reviewer agent
  • 4d5e6f7g feat: add JSON schema output formatter
  • 8h9i0j1k fix: handle empty review edge case

## Files Modified
  + src/reviewer/coordinator.py
  + src/reviewer/agents/security_agent.py
  + src/reviewer/agents/performance_agent.py
  + src/reviewer/agents/style_agent.py
  + src/reviewer/schema.py
  + src/reviewer/parallel.py
  ~ src/main.py
  ~ pyproject.toml

---

Built with opencode-calendar · Duration: 2h 14m
<!-- opencode-calendar -->
```

Each section maps to data sources:
- **Summary** → sources 1, 2, 3 (session titles, prompts, AI reasoning)
- **Agent flow** → source 8 (agent switches via session_message)
- **Tool activity** → source 7 (tool_call summary from part table)
- **Dependencies** → source 5 (dep files like pom.xml, pyproject.toml, Cargo.toml)
- **Git context** → source 9 (branch, remote, commits via `git` CLI)
- **Files Modified** → source 4 (file diffs filtered for build artifacts)
- **Duration** → source 11 (session time_created / time_updated)

---

## Project Structure

```
opencode-calendar/
├── pyproject.toml                    # Packaging & dependencies
├── .env.example                      # Configuration template
├── README.md
└── opencode_calendar/
    ├── __init__.py
    ├── cli.py                        # CLI entry point (argparse)
    ├── config.py                     # Environment variables
    ├── db.py                         # SQLite queries for opencode.db
    ├── time_utils.py                 # Half-hour rounding (floor/ceil)
    ├── summarizer.py                 # LLM prompt builder + GitHub Models API
    └── calendar_client.py            # Google Calendar OAuth + CRUD
```

---

## Requirements

- Python 3.9+
- OpenCode (any version with SQLite session store)
- Google account (for Calendar API)
- GitHub account (for free LLM API — optional, falls back to template summary)

---

## License

MIT
