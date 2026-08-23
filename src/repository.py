import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4


SEEDED_TAGS = ["디버깅", "테스트", "설계", "도구·환경"]
OBSERVATION_KINDS = {
    "proposed", "asked", "implemented", "debugged", "stuck",
    "overrode", "deferred", "corrected", "observed",
}


def root_path():
    # 빈 문자열은 "설정하지 않음"으로 친다. os.environ.get의 기본값만 쓰면
    # DEVPROFILE_ROOT=""가 Path("")로 넘어가 cwd가 되고, 학생 프로필이 그때그때
    # 작업하던 디렉터리에 흩어진다. 역량은 프로젝트가 아니라 사람에 붙는다(DESIGN §4).
    return Path(os.environ.get("DEVPROFILE_ROOT") or Path.home() / ".devprofile")


def _compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _pretty(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def parse_time(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def iso_time(value=None):
    value = parse_time(value) if value is not None else datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def ensure_root():
    root = root_path()
    (root / "raw").mkdir(parents=True, exist_ok=True)
    (root / "archive").mkdir(parents=True, exist_ok=True)
    tags_path = root / "tags.json"
    if not tags_path.exists():
        tags_path.write_text(_pretty({
            "tags": [{"name": name, "status": "active", "occurrences": 2} for name in SEEDED_TAGS],
        }), encoding="utf-8")
    profile_path = root / "profile.json"
    if not profile_path.exists():
        profile_path.write_text(_pretty({
            "anonymousId": f"anon_{uuid4()}", "track": None, "goal": None,
        }), encoding="utf-8")
    return root


def append_raw(event, now=None):
    root = ensure_root()
    current = parse_time(now) if now is not None else datetime.now(timezone.utc)
    with (root / "raw" / f"{current.astimezone(timezone.utc).date().isoformat()}.jsonl").open(
        "a", encoding="utf-8"
    ) as stream:
        stream.write(_compact(event) + "\n")


def read_json_lines(path):
    # str.splitlines()를 쓰면 안 된다. 파이썬은 U+2028/U+2029/U+0085 같은 문자에서도 줄을
    # 나누는데, 그 문자는 학생이 친 prompt.text 안에 그대로 들어올 수 있다. 그러면 JSON 한
    # 줄이 두 조각으로 갈라져 이후 모든 읽기가 실패하고, 훅의 바깥 except가 그것을 삼켜
    # 플러그인이 조용히 죽는다. 구분자는 개행뿐이다(JS 원본의 /\r?\n/와 같다).
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    return [json.loads(line) for line in text.replace("\r\n", "\n").split("\n") if line]


def read_observations():
    return read_json_lines(ensure_root() / "obs.jsonl")


def write_observations(observations):
    for observation in observations:
        kinds = observation.get("kind")
        if not isinstance(kinds, list) or not kinds or any(kind not in OBSERVATION_KINDS for kind in kinds):
            raise ValueError("관측 kind에는 허용된 행동 동사만 저장할 수 있습니다")
    body = "" if not observations else "\n".join(_compact(item) for item in observations) + "\n"
    (ensure_root() / "obs.jsonl").write_text(body, encoding="utf-8")


def read_raw_events():
    raw_dir = ensure_root() / "raw"
    return [event for path in sorted(raw_dir.glob("*.jsonl")) for event in read_json_lines(path)]


def unextracted_raw():
    events = read_raw_events()
    extracted = {
        ref for event in events if event.get("e") == "extracted" for ref in event.get("refs", [])
    }
    return [
        event for event in events
        if event.get("e") != "extracted" and event.get("rid") and event["rid"] not in extracted
    ]


def mark_extracted(events, now=None):
    refs = [event["rid"] for event in events if event.get("rid")]
    if refs:
        append_raw({"t": iso_time(now), "e": "extracted", "refs": refs}, now)


def read_tags():
    return json.loads((ensure_root() / "tags.json").read_text(encoding="utf-8"))


def read_profile():
    return json.loads((ensure_root() / "profile.json").read_text(encoding="utf-8"))


def write_profile(profile):
    (ensure_root() / "profile.json").write_text(_pretty(profile), encoding="utf-8")


def write_tags(tags):
    (ensure_root() / "tags.json").write_text(_pretty(tags), encoding="utf-8")


def purge_old_prompt_text(now=None):
    current = parse_time(now) if now is not None else datetime.now(timezone.utc)
    raw_dir = ensure_root() / "raw"
    all_events = read_raw_events()
    extracted_at = {}
    for event in all_events:
        if event.get("e") == "extracted":
            for ref in event.get("refs", []):
                extracted_at[ref] = parse_time(event["t"])
    cutoff = current - timedelta(days=7)
    for path in raw_dir.glob("*.jsonl"):
        events = read_json_lines(path)
        changed = False
        for event in events:
            extraction_time = extracted_at.get(event.get("rid"))
            if extraction_time is None or extraction_time > cutoff:
                continue
            field = "text" if event.get("e") == "prompt" else "tail" if event.get("e") == "turn_end" else None
            if field is None or field not in event:
                continue
            del event[field]
            event["purged"] = True
            changed = True
        if changed:
            temporary = Path(f"{path}.{os.getpid()}.tmp")
            temporary.write_text("\n".join(_compact(item) for item in events) + "\n", encoding="utf-8")
            os.replace(temporary, path)
