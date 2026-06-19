import os
import subprocess
import json
import requests

GITHUB_MODELS_ENDPOINT = "https://models.inference.ai.azure.com/chat/completions"


def get_git_context(directories):
    if not directories:
        return {"branch": None, "remote_url": None, "commits": []}

    for directory in directories:
        if not directory or not os.path.isdir(directory):
            continue
        try:
            subprocess.run(
                ["git", "-C", directory, "rev-parse", "--git-dir"],
                capture_output=True, text=True, timeout=5,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, TimeoutError):
            continue

        branch = None
        remote_url = None
        commits = []

        try:
            result = subprocess.run(
                ["git", "-C", directory, "branch", "--show-current"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        try:
            result = subprocess.run(
                ["git", "-C", directory, "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                remote_url = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        try:
            result = subprocess.run(
                ["git", "-C", directory, "log", "--oneline", "-5"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if line:
                        commits.append(line)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return {"branch": branch, "remote_url": remote_url, "commits": commits}

    return {"branch": None, "remote_url": None, "commits": []}


def extract_project_name(directory):
    if not directory:
        return None
    name = os.path.basename(os.path.normpath(directory))
    return name if name and name != "/" else None


def build_block_prompt(sessions, todos, user_texts, assistant_texts,
                       reasoning_parts, diffs, dep_files,
                       tool_summary, tool_details, agent_flow,
                       git_context, dirs):
    total_duration = 0
    total_tokens_in = 0
    total_tokens_out = 0
    total_tokens_reason = 0
    total_additions = 0
    total_deletions = 0
    total_files = 0
    agents_used = set()
    models_used = set()
    session_titles = []

    for s in sessions:
        total_duration += (s["time_updated"] - s["time_created"])
        total_tokens_in += s["tokens_input"]
        total_tokens_out += s["tokens_output"]
        total_tokens_reason += (s.get("tokens_reasoning") or 0)
        total_additions += s["summary_additions"]
        total_deletions += s["summary_deletions"]
        total_files += s["summary_files"]
        agents_used.add(s["agent"])
        session_titles.append(s["title"])
        try:
            model_data = json.loads(s["model"]) if isinstance(s["model"], str) else s["model"]
            mid = model_data.get("id") or model_data.get("modelID")
            if mid:
                models_used.add(mid)
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

    duration_min = round(total_duration / 60000.0, 1)
    project_names = [extract_project_name(d) for d in dirs if d]
    project_names = [p for p in project_names if p]

    lines = []
    lines.append("You are a AI Systems engineer summarizing AI-assisted coding sessions.")
    lines.append("")
    lines.append("Write a concise engineering summary (2-4 paragraphs) covering:")
    lines.append("1. The problem or requirement being addressed")
    lines.append("2. The solution and design decisions")
    lines.append("3. Libraries, code, and AI design patterns used to accomplish the solution")
    lines.append("")
    lines.append("Writing using AI system design language and using a format for humans to easily scan the text without using fluff. Avoid markdown")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append(f"Work Block: {len(sessions)} session{'s' if len(sessions) != 1 else ''} · {', '.join(project_names[:3])}")
    lines.append(f"Duration: {duration_min} minutes")
    lines.append(f"Agents: {', '.join(sorted(agents_used))}")
    lines.append(f"Models: {', '.join(sorted(models_used))}")
    lines.append(f"File Changes: +{total_additions}/-{total_deletions} across {total_files} files")
    lines.append(f"Tokens: {total_tokens_in:,} input / {total_tokens_out:,} output")
    if total_tokens_reason:
        lines.append(f"         {total_tokens_reason:,} reasoning tokens")
    lines.append("")

    if session_titles:
        lines.append("Session Titles:")
        for t in session_titles:
            lines.append(f"  - {t}")
        lines.append("")

    if git_context["branch"]:
        lines.append(f"Git Branch: {git_context['branch']}")
    if git_context["remote_url"]:
        lines.append(f"Git Remote: {git_context['remote_url']}")
    if git_context["commits"]:
        lines.append("Recent Commits:")
        for c in git_context["commits"]:
            lines.append(f"  - {c}")
    lines.append("")

    if todos:
        completed = [t for t in todos if t["status"] == "completed"]
        pending = [t for t in todos if t["status"] != "completed"]
        lines.append(f"Tasks: {len(completed)} completed")
        for t in completed:
            lines.append(f"  ✓ {t['content']}")
        if pending:
            lines.append(f"  ○ {len(pending)} remaining")
            for t in pending:
                lines.append(f"    {t['content']}")
        lines.append("")

    if diffs:
        lines.append("Files Modified:")
        for d in diffs:
            status_icon = {"added": "+", "modified": "~", "deleted": "-"}.get(d["status"], "*")
            lines.append(f"  {status_icon} {d['file']} ({d['additions']}+, {d['deletions']}-)")
        lines.append("")

    if dep_files:
        lines.append("Dependency Files Changed:")
        for f in dep_files:
            lines.append(f"  - {f}")
        lines.append("")

    if tool_summary:
        lines.append("AI Tool Activity:")
        for name, count in tool_summary.items():
            lines.append(f"  • {name}: {count}")
        if tool_details.get("reads"):
            lines.append("Key files explored:")
            for f in tool_details["reads"]:
                lines.append(f"    {f}")
        if tool_details.get("commands"):
            lines.append("Key commands run:")
            for c in tool_details["commands"]:
                lines.append(f"    {c}")
        lines.append("")

    if agent_flow:
        seen = []
        for a in agent_flow:
            if not seen or seen[-1] != a:
                seen.append(a)
        lines.append(f"AI Workflow: {' → '.join(seen)}")
        lines.append("")

    if user_texts:
        lines.append("User Requests:")
        for i, u in enumerate(user_texts):
            preview = u["text"][:500] if i == 0 else u["text"][:250]
            lines.append(f"  [{i}] {preview}")
        lines.append("")

    if assistant_texts:
        lines.append("Key Decisions:")
        for i, a in enumerate(assistant_texts[:3]):
            lines.append(f"  [{i}] {a['text'][:400]}")
        lines.append("")

    if reasoning_parts:
        lines.append("Architectural Reasoning:")
        for r in reasoning_parts[:3]:
            lines.append(f"  - {r['text'][:300]}")
        lines.append("")

    return "\n".join(lines)


def generate_summary_github(prompt_text, github_token, model="gpt-4o-mini"):
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt_text}],
        "max_tokens": 600,
        "temperature": 0.3,
    }

    resp = requests.post(
        GITHUB_MODELS_ENDPOINT,
        headers=headers,
        json=payload,
        timeout=30,
    )

    if resp.status_code != 200:
        raise RuntimeError(
            f"GitHub Models API returned {resp.status_code}: {resp.text[:300]}"
        )

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def generate_template_summary(sessions, diffs, todos):
    lines = [
        f"AI Project: {len(sessions)} session{'s' if len(sessions) != 1 else ''}",
    ]
    if diffs:
        lines.append(f"Files: {len(diffs)} changed")
    if todos:
        lines.append(f"Tasks: {len(todos)} total")
    return "\n".join(lines) + "\n\n(LLM summary unavailable — template fallback)"


def generate_block_summary(sessions, todos, user_texts, assistant_texts,
                           reasoning_parts, diffs, dep_files,
                           tool_summary, tool_details, agent_flow,
                           git_context, dirs, config):
    prompt = build_block_prompt(
        sessions, todos, user_texts, assistant_texts,
        reasoning_parts, diffs, dep_files,
        tool_summary, tool_details, agent_flow,
        git_context, dirs,
    )

    summary = None
    if config.get("github_token"):
        try:
            summary = generate_summary_github(
                prompt, config["github_token"], config.get("github_model", "gpt-4o-mini")
            )
        except Exception:
            summary = None

    if not summary:
        summary = generate_template_summary(sessions, diffs, todos)

    return summary, git_context
