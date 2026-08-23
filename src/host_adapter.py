import re


def _line_count(text):
    if not text:
        return 0
    return len(re.split(r"\r?\n", str(text)))


def normalize_write(payload):
    tool_input = payload.get("tool_input") or {}
    tool_name = payload.get("tool_name")
    if tool_name == "Edit":
        return [{
            "path": tool_input.get("file_path") or tool_input.get("path"),
            "d": _line_count(tool_input.get("new_string")) - _line_count(tool_input.get("old_string")),
        }]
    if tool_name == "Write":
        return [{
            "path": tool_input.get("file_path") or tool_input.get("path"),
            "d": _line_count(tool_input.get("content")),
        }]
    if tool_name == "apply_patch":
        return _parse_patch(tool_input.get("patch") or tool_input.get("input") or "")
    if tool_name == "Bash":
        command = tool_input.get("command") or ""
        return _parse_patch(command) if "*** Begin Patch" in command else []
    return []


def _parse_patch(patch):
    writes = []
    current = None
    for line in re.split(r"\r?\n", str(patch)):
        match = re.match(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", line)
        if match:
            current = {"path": match.group(1), "added": 0, "removed": 0}
            writes.append(current)
        elif current and line.startswith("+") and not line.startswith("+++"):
            current["added"] += 1
        elif current and line.startswith("-") and not line.startswith("---"):
            current["removed"] += 1
    return [{"path": item["path"], "d": item["added"] - item["removed"]} for item in writes]


def headless_invocation(host, prompt):
    if host == "codex":
        return ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", prompt]
    return ["claude", "-p", "--tools", "", "--disable-slash-commands", prompt]


FORMS = {
    "침묵 대행": "silent", "시범": "demonstration", "골격": "skeleton",
    "설계→구현 분리": "design_split", "구현→검수 분리": "implementation_review",
}


def answer_form(message):
    first_line = re.split(r"\r?\n", str(message or ""), maxsplit=1)[0]
    match = re.match(r"^\s*\[([^]]+)\]", first_line)
    return FORMS.get(match.group(1).strip()) if match else None


def onboarding_from_answer(message):
    first_line = re.split(r"\r?\n", str(message or ""), maxsplit=1)[0]
    match = re.match(r"^\s*\[학습자 프로필 track=(AI|풀스택|클라우드) goal=([^]]+)\]", first_line)
    return {"track": match.group(1), "goal": match.group(2).strip()} if match else None
