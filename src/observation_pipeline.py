from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .extractor import extract
from .repository import (
    iso_time, mark_extracted, parse_time, read_observations, read_tags,
    unextracted_raw, write_observations, write_tags,
)


IDLE = timedelta(minutes=30)


def _same_competency(left, right):
    return len(left) == len(right) and all(tag in right for tag in left)


def _update_tag_occurrences(candidates):
    document = read_tags()
    by_name = {tag["name"]: tag for tag in document["tags"]}
    names = dict.fromkeys(name for candidate in candidates for name in candidate["comp"])
    for name in names:
        tag = by_name.get(name)
        if tag:
            tag["occurrences"] += 1
            if tag["occurrences"] >= 2:
                tag["status"] = "active"
        else:
            created = {"name": name, "status": "pending", "occurrences": 1}
            document["tags"].append(created)
            by_name[name] = created
    write_tags(document)


def process_extraction(payload, raw=None):
    raw = unextracted_raw() if raw is None else raw
    now = parse_time(payload.get("now")) if payload.get("now") else datetime.now(timezone.utc)
    observations = read_observations()
    for observation in observations:
        if observation.get("status") == "open" and now - parse_time(observation["t1"]) >= IDLE:
            observation["status"] = "closed"
    opened = [item for item in observations if item.get("status") == "open"]
    recovered_tail = next(
        (event for event in reversed(raw) if event.get("e") == "turn_end" and event.get("tail")), None
    )
    candidates = extract({
        "raw": raw, "open": opened, "tags": read_tags()["tags"],
        "answer": payload.get("last_assistant_message") or (recovered_tail["tail"] if recovered_tail else ""),
    }, payload)
    _update_tag_occurrences(candidates)

    for candidate in candidates:
        for observation in observations:
            if observation.get("status") == "open" and not _same_competency(observation["comp"], candidate["comp"]):
                observation["status"] = "closed"
        existing = next((
            observation for observation in observations
            if observation.get("status") == "open" and _same_competency(observation["comp"], candidate["comp"])
        ), None)
        if existing:
            existing["t1"] = iso_time(now)
            existing["kind"].extend(candidate["kind"])
            existing["text"] = candidate["text"]
            existing["src"] = list(dict.fromkeys(existing["src"] + candidate["src"]))
            if candidate["status"] == "closed" or payload.get("session_ended"):
                existing["status"] = "closed"
        else:
            observations.append({
                "id": f"o_{uuid4()}", "t0": iso_time(now), "t1": iso_time(now), **candidate,
                "status": "closed" if candidate["status"] == "closed" or payload.get("session_ended") else "open",
            })
    if payload.get("session_ended"):
        for observation in observations:
            if observation.get("status") == "open":
                observation["status"] = "closed"
    write_observations(observations)
    mark_extracted(raw, now)


def close_open_observations(now=None):
    current = parse_time(now) if now is not None else datetime.now(timezone.utc)
    observations = read_observations()
    changed = False
    for observation in observations:
        if observation.get("status") == "open":
            observation["status"] = "closed"
            observation["t1"] = iso_time(current)
            changed = True
    if changed:
        write_observations(observations)
