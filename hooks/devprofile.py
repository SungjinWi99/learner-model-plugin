#!/usr/bin/env python3
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.decider import decide
from src.host_adapter import answer_form, normalize_write, onboarding_from_answer
from src.observation_pipeline import close_open_observations, process_extraction
from src.recorder import (
    record_auto_slack, record_injection, record_prompt, record_turn_end, record_write,
)
from src.renderer import render_injection, render_onboarding, render_profile
from src.repository import (
    iso_time, parse_time, purge_old_prompt_text, read_observations, read_profile,
    read_raw_events, read_tags, unextracted_raw, write_observations, write_profile,
)
from src.retriever import retrieve
from src.submission import approve_draft, create_draft
from src.tagger import tag_prompt


def _metrics(profile):
    return profile.setdefault("metrics", {"overrides": 0, "autoSilenceTransitions": 0, "flips": 0})


def main():
    if os.environ.get("DEVPROFILE_MODEL_CALL") == "1":
        return
    raw_input = sys.stdin.read().lstrip("\ufeff")
    payload = {}
    try:
        payload = json.loads(raw_input or "{}")
        event_name = payload.get("hook_event_name")
        if event_name == "PostToolUse":
            record_write(payload, normalize_write(payload))
        elif event_name == "Stop":
            profile = read_profile()
            onboarding = onboarding_from_answer(payload.get("last_assistant_message"))
            if onboarding:
                profile.update(onboarding)
            recommended = next((
                event for event in reversed(read_raw_events())
                if event.get("e") == "inject" and event.get("sid") == (payload.get("session_id") or "")
            ), None)
            now = parse_time(payload["now"]) if payload.get("now") else datetime.now(timezone.utc)
            flip = record_turn_end(
                payload, recommended.get("form") if recommended else None,
                answer_form(payload.get("last_assistant_message")), now,
            )
            if flip:
                _metrics(profile)["flips"] += 1
            write_profile(profile)
            current_raw = [
                event for event in unextracted_raw()
                if event.get("sid") == (payload.get("session_id") or "")
            ]
            process_extraction(payload, current_raw)
        elif event_name == "SessionStart":
            backlog = unextracted_raw()
            if backlog:
                process_extraction({**payload, "session_ended": True}, backlog)
            else:
                close_open_observations(payload.get("now"))
            purge_old_prompt_text(payload.get("now"))
            onboarding = render_onboarding(read_profile())
            if onboarding:
                sys.stdout.write(onboarding)
        elif event_name == "UserPromptSubmit":
            prompt_event = record_prompt(payload)
            profile = read_profile()
            command = str(payload.get("prompt") or "").strip()
            if command == "/devprofile profile":
                sys.stdout.write(render_profile(profile, read_observations())[:10000])
                return
            if command == "/devprofile submit draft":
                target = create_draft(
                    Path(payload.get("cwd") or Path.cwd()) / "devprofile-submission.md",
                    render_profile(profile, read_observations()),
                )
                sys.stdout.write(
                    f"제출 사본: {target}\n원하지 않는 관측을 사본에서 지운 뒤 "
                    f"/devprofile submit approve {target} 로 명시적으로 승인하세요."
                )
                return
            approve_prefix = "/devprofile submit approve "
            if command.startswith(approve_prefix):
                target = command[len(approve_prefix):].strip()
                try:
                    approve_draft(target)
                    sys.stdout.write("검토한 제출 사본을 클립보드에 복사하고 폼을 열었습니다. 학생이 직접 붙여넣고 제출하세요.")
                except Exception as error:
                    sys.stdout.write(f"DevProfile 제출 실패: {error}")
                return
            if profile.get("slack") == "none" and re.search(r"(?:설계|구조|어떤\s*단계|어떻게\s*접근)", str(payload.get("prompt") or "")):
                profile["slack"] = "available"
                write_profile(profile)
            if prompt_event["override"]:
                _metrics(profile)["overrides"] += 1
                prompts = [
                    event for event in read_raw_events()
                    if event.get("e") == "prompt" and event.get("sid") == (payload.get("session_id") or "")
                ]
                consecutive = len(prompts[-3:]) == 3 and all(event.get("override") for event in prompts[-3:])
                whole_session = bool(re.search(r"이번\s*세션\s*내내", str(payload.get("prompt") or "")))
                if (consecutive or whole_session) and profile.get("slack") != "none":
                    profile["slack"] = "none"
                    _metrics(profile)["autoSilenceTransitions"] += 1
                    write_profile(profile)
                    last_injection = next((event for event in reversed(read_raw_events()) if event.get("e") == "inject"), None)
                    now = datetime.now(timezone.utc)
                    observations = read_observations()
                    observations.append({
                        "id": f"o_auto_slack_{int(now.timestamp() * 1000)}",
                        "t0": iso_time(now), "t1": iso_time(now),
                        "comp": last_injection["comp"] if last_injection and last_injection.get("comp") else ["설계"],
                        "kind": ["overrode"], "text": "3회 연속 우회로 여유가 자동으로 없음으로 전환됨",
                        "status": "closed", "src": [event["rid"] for event in prompts[-3:]],
                    })
                    write_observations(observations)
                    record_auto_slack(payload, now)
                write_profile(profile)
                return
            tags = read_tags()["tags"]
            # pending 역량도 개입 결정에 쓴다. 2회 승격은 태그 목록의 파편화를 막는 규칙이다.
            tagged = tag_prompt(
                payload.get("prompt"), tags,
                os.environ.get("DEVPROFILE_HOST") or payload.get("host") or "claude",
            )
            relevant = retrieve(tagged)
            reason_counts = {}
            for event in read_raw_events():
                if event.get("e") == "inject" and event.get("observationId"):
                    observation_id = event["observationId"]
                    reason_counts[observation_id] = reason_counts.get(observation_id, 0) + 1
            decision = decide(
                payload.get("prompt"), tagged, relevant, profile.get("slack"),
                profile.get("recentInterventions"), reason_counts,
            )
            if decision["reason"] == "no_slack":
                now = datetime.now(timezone.utc)
                observations = read_observations()
                observations.append({
                    "id": f"o_deferred_{int(now.timestamp() * 1000)}",
                    "t0": iso_time(now), "t1": iso_time(now), "comp": tagged,
                    "kind": ["deferred"],
                    "text": f"여유 없음 상태에서 {', '.join(tagged)} 관련 작업을 미룬 레슨으로 남김",
                    "status": "closed", "src": [prompt_event["rid"]],
                })
                write_observations(observations)
            if decision["form"] != "silent":
                record_injection(payload, decision)
                profile["recentInterventions"] = [
                    *(profile.get("recentInterventions") or []), decision["focus"],
                ][-8:]
                write_profile(profile)
                sys.stdout.write(render_injection(decision, relevant))
    except Exception as error:
        if payload.get("hook_event_name") in {"Stop", "SessionStart"}:
            sys.stderr.write(f"devprofile 추출기 실패: {error}\n")
        # 훅 오류가 학생의 프롬프트를 막지 않게 한다. 성공한 raw append만 진실로 취급한다.


if __name__ == "__main__":
    main()
