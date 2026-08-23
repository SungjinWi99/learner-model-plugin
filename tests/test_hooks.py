import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "devprofile.py"
STUB = ROOT / "tests" / "fixtures" / "extractor_stub.py"


def run_hook(tmp_path, name, payload, extra_env=None):
    profile_root = tmp_path / name
    env = {
        **os.environ,
        "HOME": str(profile_root / "home"),
        "USERPROFILE": str(profile_root / "home"),
        "DEVPROFILE_ROOT": str(profile_root),
        **(extra_env or {}),
    }
    result = subprocess.run(
        [sys.executable, str(HOOK)], input=json.dumps(payload, ensure_ascii=False),
        text=True, capture_output=True, timeout=30, env=env, check=False,
    )
    return profile_root, result


def raw_events(profile_root):
    return [
        json.loads(line)
        for path in sorted((profile_root / "raw").glob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n") if line
    ]


def write_raw(profile_root, date, events):
    raw_dir = profile_root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{date}.jsonl").write_text(
        "\n".join(json.dumps(event, ensure_ascii=False, separators=(",", ":")) for event in events) + "\n",
        encoding="utf-8",
    )


def observations(profile_root):
    path = profile_root / "obs.jsonl"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return [json.loads(line) for line in text.split("\n") if line]


def extractor_env(output):
    return {
        "DEVPROFILE_EXTRACTOR_COMMAND": shlex.join([sys.executable, str(STUB)]),
        "DEVPROFILE_STUB_OUTPUT": json.dumps(output, ensure_ascii=False),
    }


def keyword_tagger_env():
    return {"PATH": str(Path(sys.executable).parent), "DEVPROFILE_HOST": "claude"}


def llm_tagger_env(output, input_file=None):
    env = {
        "DEVPROFILE_TAGGER_COMMAND": shlex.join([sys.executable, str(STUB)]),
        "DEVPROFILE_STUB_OUTPUT": json.dumps(output, ensure_ascii=False),
    }
    if input_file:
        env["DEVPROFILE_STUB_INPUT_FILE"] = str(input_file)
    return env


def write_observations(profile_root, items):
    profile_root.mkdir(parents=True, exist_ok=True)
    (profile_root / "obs.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in items) + "\n",
        encoding="utf-8",
    )


def test_PostToolUse_Claude_Edit은_코드_본문_없이_쓰기_사건을_기록한다(tmp_path):
    profile_root, result = run_hook(tmp_path, "claude-edit", {
        "hook_event_name": "PostToolUse", "session_id": "claude-1", "tool_name": "Edit",
        "tool_input": {
            "file_path": "src/graph.js", "old_string": "return old;",
            "new_string": "const value = build();\nreturn value;",
        },
    })
    assert result.returncode == 0, result.stderr
    events = raw_events(profile_root)
    assert len(events) == 1
    assert {key: events[0][key] for key in ("e", "sid", "path", "d")} == {
        "e": "write", "sid": "claude-1", "path": "src/graph.js", "d": 1,
    }
    assert not re.search(r"return old|const value|return value", json.dumps(events[0]))


def test_PostToolUse_Codex_apply_patch와_Bash_경유_패치를_같은_쓰기_사건으로_기록한다(tmp_path):
    patch = "\n".join([
        "*** Begin Patch", "*** Update File: src/worker.js", "@@", "-const secret = 1;",
        "+const secret = 2;", "+run(secret);", "*** End Patch",
    ])
    runs = [
        run_hook(tmp_path, "codex-patch", {
            "hook_event_name": "PostToolUse", "session_id": "codex-1",
            "tool_name": "apply_patch", "tool_input": {"patch": patch},
        }),
        run_hook(tmp_path, "codex-bash", {
            "hook_event_name": "PostToolUse", "session_id": "codex-2", "tool_name": "Bash",
            "tool_input": {"command": f"apply_patch <<'PATCH'\n{patch}\nPATCH"},
        }),
    ]
    for profile_root, result in runs:
        assert result.returncode == 0, result.stderr
        events = raw_events(profile_root)
        assert len(events) == 1
        assert (events[0]["e"], events[0]["path"], events[0]["d"]) == ("write", "src/worker.js", 1)
        assert not re.search(r"const secret|run\(secret\)", json.dumps(events[0]))


def test_Stop_희소한_관측을_upsert하고_세_종료_조건에서_open_에피소드를_닫는다(tmp_path):
    candidate = {
        "comp": ["테스트"], "kind": ["asked"], "text": "테스트 실패 원인을 질문함",
        "status": "open", "src": ["stop-1@10:00..10:05"],
    }
    root, result = run_hook(tmp_path, "stop-upsert", {
        "hook_event_name": "Stop", "session_id": "stop-1", "now": "2026-08-23T10:05:00.000Z",
        "last_assistant_message": "[설계→구현 분리] 먼저 테스트 전략을 말해 주세요.",
    }, extractor_env([candidate]))
    assert result.returncode == 0, result.stderr
    assert len(observations(root)) == 1 and observations(root)[0]["status"] == "open"

    root, result = run_hook(tmp_path, "stop-session-end", {
        "hook_event_name": "Stop", "session_id": "stop-2", "now": "2026-08-23T10:05:00.000Z",
        "session_ended": True,
    }, extractor_env([candidate]))
    assert result.returncode == 0, result.stderr
    assert observations(root)[0]["status"] == "closed"

    tag_root = tmp_path / "stop-tag-change"
    write_observations(tag_root, [{
        "id": "o_old", "t0": "2026-08-23T09:55:00.000Z", "t1": "2026-08-23T10:00:00.000Z",
        "comp": ["테스트"], "kind": ["asked"], "text": "테스트를 질문함", "status": "open", "src": ["old"],
    }])
    root, result = run_hook(tmp_path, "stop-tag-change", {
        "hook_event_name": "Stop", "session_id": "stop-3", "now": "2026-08-23T10:05:00.000Z",
    }, extractor_env([{**candidate, "comp": ["설계"], "text": "설계를 제안함"}]))
    assert result.returncode == 0, result.stderr
    assert next(item for item in observations(root) if item["id"] == "o_old")["status"] == "closed"
    assert len(observations(root)) == 2

    idle_root = tmp_path / "stop-inactivity"
    write_observations(idle_root, [{
        "id": "o_idle", "t0": "2026-08-23T09:00:00.000Z", "t1": "2026-08-23T09:10:00.000Z",
        "comp": ["테스트"], "kind": ["asked"], "text": "테스트를 질문함", "status": "open", "src": ["idle"],
    }])
    root, result = run_hook(tmp_path, "stop-inactivity", {
        "hook_event_name": "Stop", "session_id": "stop-4", "now": "2026-08-23T10:00:00.000Z",
    }, extractor_env([]))
    assert result.returncode == 0, result.stderr
    assert observations(root)[0]["status"] == "closed"

    root, result = run_hook(tmp_path, "stop-sparse", {
        "hook_event_name": "Stop", "session_id": "stop-5", "now": "2026-08-23T10:00:00.000Z",
    }, extractor_env([]))
    assert result.returncode == 0, result.stderr
    assert observations(root) == []


def test_Stop_추출기가_실패하면_raw를_보존하고_extracted_표시를_남기지_않는다(tmp_path):
    profile_root = tmp_path / "stop-extractor-failure"
    write_raw(profile_root, "2026-08-23", [{
        "rid": "r_pending", "t": "2026-08-23T10:00:00.000Z", "e": "prompt", "sid": "fail-1",
        "text": "테스트 전략을 정리해줘",
    }])
    _, result = run_hook(tmp_path, "stop-extractor-failure", {
        "hook_event_name": "Stop", "session_id": "fail-1", "now": "2026-08-23T10:01:00.000Z",
    }, {**extractor_env([]), "DEVPROFILE_STUB_FAIL": "1"})
    assert result.returncode == 0
    assert "추출기" in result.stderr
    events = raw_events(profile_root)
    assert any(event.get("rid") == "r_pending" and event.get("text") == "테스트 전략을 정리해줘" for event in events)
    assert not any(event.get("e") == "extracted" for event in events)


def test_SessionStart_밀린_raw를_회수하고_두_번째_실행에서도_관측을_중복하지_않는다(tmp_path):
    profile_root = tmp_path / "session-recovery"
    write_raw(profile_root, "2026-08-22", [{
        "rid": "r_backlog", "t": "2026-08-22T10:00:00.000Z", "e": "prompt",
        "sid": "old-session", "text": "도구 설정 오류를 디버깅해줘",
    }])
    recovered = [{
        "comp": ["도구·환경"], "kind": ["debugged"], "text": "도구 설정 오류를 추적함",
        "status": "closed", "src": ["old-session@10:00..10:05"],
    }]
    _, first = run_hook(tmp_path, "session-recovery", {
        "hook_event_name": "SessionStart", "session_id": "new-session", "now": "2026-08-23T09:00:00.000Z",
    }, extractor_env(recovered))
    assert first.returncode == 0, first.stderr
    assert len(observations(profile_root)) == 1
    assert "트랙" in first.stdout and "목표" in first.stdout
    _, second = run_hook(tmp_path, "session-recovery", {
        "hook_event_name": "SessionStart", "session_id": "new-session-2", "now": "2026-08-23T09:01:00.000Z",
    }, extractor_env(recovered))
    assert second.returncode == 0, second.stderr
    assert len(observations(profile_root)) == 1
    assert sum(event.get("e") == "extracted" for event in raw_events(profile_root)) == 1


def test_Stop과_SessionStart_잘린_답변_말미로_복구하고_write를_학생_작업으로_추론하지_않게_한다(tmp_path):
    long_answer = f"삭제될머리{'가' * 2100}보존될말미"
    root, result = run_hook(tmp_path, "turn-end-tail", {
        "hook_event_name": "Stop", "session_id": "tail-session", "now": "2026-08-23T10:00:00.000Z",
        "last_assistant_message": long_answer,
    }, extractor_env([]))
    assert result.returncode == 0, result.stderr
    turn_end = next(event for event in raw_events(root) if event["e"] == "turn_end")
    assert len(turn_end["tail"]) == 2000
    assert "삭제될머리" not in turn_end["tail"] and turn_end["tail"].endswith("보존될말미")

    profile_root = tmp_path / "recovered-tail"
    write_raw(profile_root, "2026-08-22", [
        {"rid": "r_prompt", "t": "2026-08-22T10:00:00.000Z", "e": "prompt", "sid": "old", "text": "기능을 구현해줘"},
        {"rid": "r_write", "t": "2026-08-22T10:01:00.000Z", "e": "write", "sid": "old", "path": "src/a.js", "d": 12},
        {"rid": "r_tail", "t": "2026-08-22T10:02:00.000Z", "e": "turn_end", "sid": "old", "tail": "복구된 에이전트 답변 말미"},
    ])
    input_file = tmp_path / "recovered-extractor-input.txt"
    _, result = run_hook(tmp_path, "recovered-tail", {
        "hook_event_name": "SessionStart", "session_id": "new", "now": "2026-08-23T10:00:00.000Z",
    }, {**extractor_env([]), "DEVPROFILE_STUB_INPUT_FILE": str(input_file)})
    assert result.returncode == 0, result.stderr
    extractor_input = input_file.read_text(encoding="utf-8")
    assert "write 사건은 학생이 아니라 에이전트" in extractor_input
    assert "대화 밖에서 학생이 한 작업은 보이지 않으므로 추론하지 마세요" in extractor_input
    assert '"answer":"복구된 에이전트 답변 말미"' in extractor_input


def test_UserPromptSubmit_태그_필터_뒤_최신_8개_관측과_권장_형태와_개입_사유를_10000자_안에_주입한다(tmp_path):
    profile_root = tmp_path / "prompt-retrieval"
    test_items = [{
        "id": f"o_test_{index}", "t0": f"2026-08-{10 + index:02d}T10:00:00.000Z",
        "t1": f"2026-08-{10 + index:02d}T10:05:00.000Z", "comp": ["테스트"], "kind": ["asked"],
        "text": f"테스트 관측 {index} {'긴내용' * 700}", "status": "closed", "src": [f"s{index}"],
    } for index in range(9)]
    write_observations(profile_root, [*test_items, {
        "id": "o_design", "t0": "2026-08-23T11:00:00.000Z", "t1": "2026-08-23T11:05:00.000Z",
        "comp": ["설계"], "kind": ["implemented"], "text": "설계 전용 관측", "status": "closed", "src": ["design"],
    }])
    _, result = run_hook(tmp_path, "prompt-retrieval", {
        "hook_event_name": "UserPromptSubmit", "session_id": "prompt-1",
        "prompt": "테스트 전략을 추가해줘", "cwd": "/tmp/project",
    }, keyword_tagger_env())
    assert result.returncode == 0, result.stderr
    # 10,000자는 Claude Code의 하드 상한, DESIGN §7의 목표 주입량은 1,000~2,000자다.
    assert len(result.stdout) <= 10000
    assert len(result.stdout) <= 2000, f"주입량이 §7의 목표를 넘었다: {len(result.stdout)}자"
    assert "[설계→구현 분리]" in result.stdout and "테스트 관측 8" in result.stdout
    assert "테스트 관측 0" not in result.stdout and "설계 전용 관측" not in result.stdout
    assert "개입 사유" in result.stdout
    _, trivial = run_hook(tmp_path, "prompt-trivial", {
        "hook_event_name": "UserPromptSubmit", "session_id": "prompt-2", "prompt": "README 오타 수정해줘",
    }, keyword_tagger_env())
    assert trivial.returncode == 0, trivial.stderr
    assert trivial.stdout == ""


def test_UserPromptSubmit_주입된_모델_태거가_성공하면_키워드_없이_반환한_태그를_사용한다(tmp_path):
    input_file = tmp_path / "tagger-input.txt"
    root, result = run_hook(tmp_path, "llm-tagger", {
        "hook_event_name": "UserPromptSubmit", "session_id": "tagger-session",
        "prompt": "품질 보증 전략을 추가해줘", "cwd": "/tmp/project",
    }, llm_tagger_env(["테스트"], input_file))
    assert result.returncode == 0, result.stderr
    assert "레슨 초점: 테스트" in result.stdout
    assert "품질 보증 전략을 추가해줘" in input_file.read_text(encoding="utf-8")
    assert next(event for event in raw_events(root) if event["e"] == "inject")["comp"] == ["테스트"]


def test_UserPromptSubmit_연속_우회는_현재_세션_안에서만_센다(tmp_path):
    for sid in ["session-a", "session-b", "session-c"]:
        _, result = run_hook(tmp_path, "cross-session-overrides", {
            "hook_event_name": "UserPromptSubmit", "session_id": sid, "prompt": "그냥 해줘",
        }, keyword_tagger_env())
        assert result.returncode == 0, result.stderr
    root = tmp_path / "cross-session-overrides"
    profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    assert profile.get("slack") != "none"
    assert profile["metrics"]["autoSilenceTransitions"] == 0
    assert not any(event.get("e") == "auto_slack" for event in raw_events(root))


def test_UserPromptSubmit_3회_연속_우회는_여유를_none으로_바꾸고_그_전환을_관측으로_남긴다(tmp_path):
    for _ in range(3):
        _, result = run_hook(tmp_path, "three-overrides", {
            "hook_event_name": "UserPromptSubmit", "session_id": "override-session", "prompt": "그냥 해줘",
        }, keyword_tagger_env())
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""
    root = tmp_path / "three-overrides"
    profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    assert profile["slack"] == "none"
    flip = next((item for item in observations(root) if "자동" in item["text"]), None)
    assert flip and flip["kind"] == ["overrode"]
    assert sum(event.get("e") == "auto_slack" for event in raw_events(root)) == 1

    before = len(observations(root))
    _, trivial = run_hook(tmp_path, "three-overrides", {
        "hook_event_name": "UserPromptSubmit", "session_id": "override-session", "prompt": "테스트 오타 수정해줘",
    }, keyword_tagger_env())
    assert trivial.returncode == 0 and trivial.stdout == ""
    assert len(observations(root)) == before
    _, deferred = run_hook(tmp_path, "three-overrides", {
        "hook_event_name": "UserPromptSubmit", "session_id": "override-session", "prompt": "테스트 전략을 추가해줘",
    }, keyword_tagger_env())
    assert deferred.returncode == 0 and deferred.stdout == ""
    assert any("deferred" in item["kind"] for item in observations(root))
    _, profile_view = run_hook(tmp_path, "three-overrides", {
        "hook_event_name": "UserPromptSubmit", "session_id": "override-session", "prompt": "/devprofile profile",
    }, keyword_tagger_env())
    assert "성공 지표 (우회 + 자동침묵전환): 4" in profile_view.stdout
    cwd = tmp_path / "metrics-submission"
    cwd.mkdir()
    _, draft = run_hook(tmp_path, "three-overrides", {
        "hook_event_name": "UserPromptSubmit", "session_id": "override-session",
        "prompt": "/devprofile submit draft", "cwd": str(cwd),
    }, keyword_tagger_env())
    assert draft.returncode == 0, draft.stderr
    assert "성공 지표 (우회 + 자동침묵전환): 4" in (cwd / "devprofile-submission.md").read_text(encoding="utf-8")


def test_Stop_답변_첫_줄의_형태가_권장과_다르면_뒤집힘을_1회_집계한다(tmp_path):
    root = tmp_path / "stop-flip"
    write_raw(root, "2026-08-23", [{
        "rid": "r_inject", "t": "2026-08-23T10:00:00.000Z", "e": "inject", "sid": "flip-session",
        "comp": ["테스트"], "form": "design_split", "observationId": "o_reason",
    }])
    _, result = run_hook(tmp_path, "stop-flip", {
        "hook_event_name": "Stop", "session_id": "flip-session", "now": "2026-08-23T10:05:00.000Z",
        "last_assistant_message": "[골격] 핵심 단언문만 채워보세요.\n나머지 구조는 준비했습니다.",
    }, extractor_env([]))
    assert result.returncode == 0, result.stderr
    profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    assert profile["metrics"]["flips"] == 1
    turn_end = next(event for event in raw_events(root) if event["e"] == "turn_end")
    assert {key: turn_end[key] for key in ("recommended", "actual", "flip")} == {
        "recommended": "design_split", "actual": "skeleton", "flip": True,
    }


def test_SessionStart_정제_시점부터_7일_동안_raw_원문과_답변_말미를_보존한_뒤_폐기한다(tmp_path):
    root = tmp_path / "prompt-purge"
    write_raw(root, "2026-08-01", [
        {"rid": "r_old_prompt", "t": "2026-08-01T10:00:00.000Z", "e": "prompt", "sid": "old", "text": "정제 뒤 일주일 동안 남아야 하는 원문"},
        {"rid": "r_old_tail", "t": "2026-08-01T10:05:00.000Z", "e": "turn_end", "sid": "old", "tail": "정제 뒤 일주일 동안 남아야 하는 답변 말미"},
    ])
    _, result = run_hook(tmp_path, "prompt-purge", {
        "hook_event_name": "SessionStart", "session_id": "new", "now": "2026-08-23T10:00:00.000Z",
    }, extractor_env([{
        "comp": ["테스트"], "kind": ["asked"], "text": "테스트를 질문함", "status": "closed", "src": ["old"],
    }]))
    assert result.returncode == 0, result.stderr
    old_prompt = next(event for event in raw_events(root) if event.get("rid") == "r_old_prompt")
    old_tail = next(event for event in raw_events(root) if event.get("rid") == "r_old_tail")
    assert old_prompt["text"] == "정제 뒤 일주일 동안 남아야 하는 원문"
    assert old_tail["tail"] == "정제 뒤 일주일 동안 남아야 하는 답변 말미"
    _, result = run_hook(tmp_path, "prompt-purge", {
        "hook_event_name": "SessionStart", "session_id": "later", "now": "2026-08-31T10:00:00.001Z",
    }, extractor_env([]))
    assert result.returncode == 0, result.stderr
    old_prompt = next(event for event in raw_events(root) if event.get("rid") == "r_old_prompt")
    old_tail = next(event for event in raw_events(root) if event.get("rid") == "r_old_tail")
    assert old_prompt["purged"] is True and "text" not in old_prompt
    assert old_tail["purged"] is True and "tail" not in old_tail


def test_Stop_첫_세션_답변의_트랙과_목표만_profile에_저장하고_자가평가는_만들지_않는다(tmp_path):
    root, result = run_hook(tmp_path, "onboarding-answer", {
        "hook_event_name": "Stop", "session_id": "onboarding", "now": "2026-08-23T10:00:00.000Z",
        "last_assistant_message": "[학습자 프로필 track=AI goal=RAG 서비스를 끝까지 배포하기]\n좋아요. 이 두 가지만 기억할게요.",
    }, extractor_env([]))
    assert result.returncode == 0, result.stderr
    profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    assert profile["track"] == "AI" and profile["goal"] == "RAG 서비스를 끝까지 배포하기"
    assert "selfAssessment" not in profile


def test_UserPromptSubmit_학생이_프로필을_열람하고_제출_사본을_만들_수_있다(tmp_path):
    _, profile_view = run_hook(tmp_path, "profile-command", {
        "hook_event_name": "UserPromptSubmit", "session_id": "profile", "prompt": "/devprofile profile",
    }, keyword_tagger_env())
    assert profile_view.returncode == 0, profile_view.stderr
    assert "# 학습자 프로필" in profile_view.stdout and "익명 ID: anon_" in profile_view.stdout
    cwd = tmp_path / "submission-workspace"
    cwd.mkdir()
    _, draft = run_hook(tmp_path, "profile-command", {
        "hook_event_name": "UserPromptSubmit", "session_id": "profile",
        "prompt": "/devprofile submit draft", "cwd": str(cwd),
    }, keyword_tagger_env())
    assert draft.returncode == 0, draft.stderr
    draft_path = cwd / "devprofile-submission.md"
    assert draft_path.exists() and "익명 ID: anon_" in draft_path.read_text(encoding="utf-8")
    assert "명시적으로 승인" in draft.stdout


def test_UserPromptSubmit_아직_승격되지_않은_pending_역량도_개입_결정과_미룬_레슨에_쓴다(tmp_path):
    root, _ = run_hook(tmp_path, "pending-tag", {
        "hook_event_name": "UserPromptSubmit", "session_id": "pending-session", "prompt": "오타 수정해줘",
    }, keyword_tagger_env())
    tags_path = root / "tags.json"
    document = json.loads(tags_path.read_text(encoding="utf-8"))
    document["tags"].append({"name": "langgraph/send", "status": "pending", "occurrences": 1})
    tags_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    profile_path = root / "profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["slack"] = "none"
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    before = len(observations(root))
    _, result = run_hook(tmp_path, "pending-tag", {
        "hook_event_name": "UserPromptSubmit", "session_id": "pending-session", "prompt": "send로 팬아웃 붙여줘",
    }, keyword_tagger_env())
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    deferred = next((item for item in observations(root)[before:] if "deferred" in item["kind"]), None)
    assert deferred and deferred["comp"] == ["langgraph/send"]


def test_UserPromptSubmit_프로필이_커져도_주입량은_일정하다(tmp_path):
    """DESIGN §7: 프로필이 300개든 2,400개든 주입량은 일정하다.

    이걸 실제로 지키는 건 관측당 텍스트 절단과 상위 8개 제한이다. 바깥의 길이 상한은
    백스톱일 뿐이라, 관측 수를 늘려도 주입이 안 커지는지를 재야 한다.
    """
    def inject_with(name, count):
        write_observations(tmp_path / name, [{
            "id": f"o_{index}",
            "t0": f"2026-08-01T10:00:00.000Z",
            "t1": f"2026-08-01T10:{index % 60:02d}:00.000Z",
            "comp": ["테스트"], "kind": ["asked"],
            "text": f"테스트 관측 {index} {'긴내용' * 700}",
            "status": "closed", "src": [f"s{index}"],
        } for index in range(count)])
        _, result = run_hook(tmp_path, name, {
            "hook_event_name": "UserPromptSubmit", "session_id": "size-1",
            "prompt": "테스트 전략을 추가해줘", "cwd": "/tmp/project",
        }, keyword_tagger_env())
        assert result.returncode == 0, result.stderr
        return len(result.stdout)

    small = inject_with("size-small", 8)
    large = inject_with("size-large", 400)

    assert small > 0 and large > 0
    # 엄격 부등호다. 길이가 상한과 정확히 같다면 바깥 절단이 발동했다는 뜻이고,
    # 그건 주입량을 일정하게 유지하는 진짜 장치(상위 8개 + 관측당 절단)가 duty를
    # 못 했다는 신호다. 백스톱이 일하는 상태를 정상으로 읽으면 안 된다.
    assert large < 2000, (
        f"주입이 상한에 걸려 잘렸다({large}자). 상위 8개 제한과 관측당 절단이 "
        "먼저 일해서 상한에 닿지 않아야 한다."
    )
    assert large == small, (
        f"관측이 8개에서 400개로 늘었는데 주입량이 {small}자 → {large}자로 변했다. "
        "§7은 주입량이 프로필 크기와 무관하게 일정하다고 못 박았다."
    )


def test_UserPromptSubmit_줄바꿈으로_읽히는_유니코드가_섞인_프롬프트도_저장소를_깨뜨리지_않는다(tmp_path):
    """파이썬 str.splitlines()는 U+2028/U+2029/U+0085에서도 줄을 나눈다.

    그 문자는 학생이 붙여넣은 프롬프트에 그대로 들어올 수 있고, JSONL 한 줄이 갈라지면
    이후 모든 읽기가 실패한다. 훅의 바깥 except가 그 실패를 삼키므로 플러그인은
    종료 코드 0을 내면서 조용히 죽는다. 한 번 쓰이면 영구적이다.
    """
    for code_point in (0x2028, 0x2029, 0x0085):
        separator = chr(code_point)
        name = f"unicode-{code_point:04x}"
        _, first = run_hook(tmp_path, name, {
            "hook_event_name": "UserPromptSubmit", "session_id": "u-1",
            "prompt": f"테스트 전략을{separator}설계해줘", "cwd": "/tmp/project",
        }, keyword_tagger_env())
        assert first.returncode == 0, first.stderr

        # 저장소가 성한지는 "다음 호출이 여전히 주입하는가"로만 확인할 수 있다.
        _, second = run_hook(tmp_path, name, {
            "hook_event_name": "UserPromptSubmit", "session_id": "u-1",
            "prompt": "테스트 전략을 설계해줘", "cwd": "/tmp/project",
        }, keyword_tagger_env())
        assert second.returncode == 0, second.stderr
        assert "[설계→구현 분리]" in second.stdout, (
            f"U+{code_point:04X}가 섞인 프롬프트 뒤에 주입이 사라졌다. "
            "저장소 읽기가 깨졌고 바깥 except가 그것을 삼켰다."
        )

        # raw도 온전히 되읽혀야 한다.
        events = raw_events(tmp_path / name)
        assert sum(1 for event in events if event.get("e") == "prompt") == 2


def test_빈_DEVPROFILE_ROOT는_설정하지_않은_것으로_보고_홈_아래를_쓴다(tmp_path):
    """DEVPROFILE_ROOT=""가 Path("")로 넘어가면 cwd가 되어, 학생 프로필이 그때그때
    작업하던 프로젝트 디렉터리에 흩어진다. 역량은 프로젝트가 아니라 사람에 붙는다(DESIGN §4).
    """
    home = tmp_path / "empty-root-home"
    workdir = tmp_path / "some-project"
    workdir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({
            "hook_event_name": "UserPromptSubmit", "session_id": "empty-1",
            "prompt": "테스트 전략을 설계해줘", "cwd": str(workdir),
        }, ensure_ascii=False),
        text=True, capture_output=True, timeout=30, check=False, cwd=str(workdir),
        env={
            **os.environ, "HOME": str(home), "USERPROFILE": str(home),
            "DEVPROFILE_ROOT": "", "PATH": str(Path(sys.executable).parent),
            "DEVPROFILE_HOST": "claude",
        },
    )
    assert result.returncode == 0, result.stderr
    assert "[설계→구현 분리]" in result.stdout
    assert (home / ".devprofile" / "raw").is_dir(), "홈 아래 저장소가 만들어져야 한다"
    assert not (workdir / "raw").exists(), f"작업 디렉터리에 저장소가 생겼다: {list(workdir.iterdir())}"


def test_제출_사본_경로는_심볼릭_링크를_풀지_않고_물결도_펼친다(tmp_path):
    """Path.resolve()는 링크를 실제 위치로 바꾼다. 안내한 경로와 학생이 아는 경로가
    달라지면 제출 흐름이 헷갈린다(DESIGN §10). ~도 안 펼치면 `~` 디렉터리가 생긴다.
    """
    home = tmp_path / "home"
    real = tmp_path / "real-project"
    real.mkdir(parents=True)
    link = tmp_path / "linked-project"
    link.symlink_to(real, target_is_directory=True)

    _, result = run_hook(tmp_path, "draft-symlink", {
        "hook_event_name": "UserPromptSubmit", "session_id": "d-1",
        "prompt": "/devprofile submit draft", "cwd": str(link),
    }, {**keyword_tagger_env(), "HOME": str(home), "USERPROFILE": str(home)})
    assert result.returncode == 0, result.stderr
    assert str(link) in result.stdout, (
        f"안내된 경로가 링크를 풀어버렸다. 출력: {result.stdout!r}"
    )
    assert str(real) not in result.stdout
    assert (link / "devprofile-submission.md").exists()


def test_CLI_제출_사본_경로의_물결이_홈으로_펼쳐진다(tmp_path):
    home = tmp_path / "cli-home"
    (home / ".devprofile").mkdir(parents=True)
    workdir = tmp_path / "cli-project"
    workdir.mkdir(parents=True)
    result = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "devprofile.py"), "submit", "--draft", "~/사본.md"],
        text=True, capture_output=True, timeout=30, check=False, cwd=str(workdir),
        env={
            **os.environ, "HOME": str(home), "USERPROFILE": str(home),
            "DEVPROFILE_ROOT": str(home / ".devprofile"),
            "PATH": str(Path(sys.executable).parent), "DEVPROFILE_HOST": "claude",
        },
    )
    assert result.returncode == 0, result.stderr
    assert (home / "사본.md").exists(), f"홈에 만들어져야 한다. 출력: {result.stdout!r}"
    assert not (workdir / "~").exists(), "물결이 디렉터리 이름으로 쓰였다"
