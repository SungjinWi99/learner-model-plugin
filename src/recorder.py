import re
from uuid import uuid4

from .repository import append_raw, iso_time


def record_write(payload, writes, now=None):
    for write in writes or []:
        if not write.get("path"):
            continue
        append_raw({
            "rid": f"r_{uuid4()}", "t": iso_time(now), "e": "write",
            "sid": payload.get("session_id") or "", "tool": payload.get("tool_name") or "",
            "path": write["path"], "d": write.get("d"),
        }, now)


def is_override(text):
    return bool(re.search(r"(?:그냥|걍)\s*(?:해|해줘|해주세요)|네가\s*(?:해|해줘)|이번\s*세션\s*내내\s*(?:해|해줘)", str(text or ""), re.I))


def record_prompt(payload, now=None):
    event = {
        "rid": f"r_{uuid4()}", "t": iso_time(now), "e": "prompt",
        "sid": payload.get("session_id") or "", "cwd": payload.get("cwd") or "",
        "text": str(payload.get("prompt") or ""), "override": is_override(payload.get("prompt")),
    }
    append_raw(event, now)
    return event


def record_injection(payload, decision, now=None):
    append_raw({
        "rid": f"r_{uuid4()}", "t": iso_time(now), "e": "inject",
        "sid": payload.get("session_id") or "", "comp": [decision["focus"]] if decision.get("focus") else [],
        "form": decision["form"],
        "observationId": decision.get("observation", {}).get("id") if decision.get("observation") else None,
    }, now)


def record_auto_slack(payload, now=None):
    append_raw({
        "rid": f"r_{uuid4()}", "t": iso_time(now), "e": "auto_slack",
        "sid": payload.get("session_id") or "", "slack": "none",
    }, now)


def record_turn_end(payload, recommended, actual, now=None):
    flip = bool(recommended and actual and recommended != actual)
    append_raw({
        "rid": f"r_{uuid4()}", "t": iso_time(now), "e": "turn_end",
        "sid": payload.get("session_id") or "", "recommended": recommended or None,
        "actual": actual or None, "flip": flip,
        "tail": str(payload.get("last_assistant_message") or "")[-2000:],
    }, now)
    return flip
