import json
import os
import re
import subprocess

from .host_adapter import headless_invocation


ACTIONS = {
    "proposed", "asked", "implemented", "debugged", "stuck",
    "overrode", "deferred", "corrected", "observed",
}
AXES = {"디버깅", "테스트", "설계", "도구·환경"}


def _compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _extractor_prompt(input_data):
    return "\n".join([
        "대화에서 직접 관측한 행동만 JSON 배열로 반환하세요. 대부분은 []입니다.",
        "kind 허용값: proposed asked implemented debugged stuck overrode deferred corrected observed.",
        "판정이나 코드 본문을 쓰지 마세요. comp는 기존 태그를 우선 사용하고 새 태그는 <도메인>/<구체> 깊이만 허용합니다.",
        "raw의 write 사건은 학생이 아니라 에이전트가 PostToolUse로 남긴 도구 호출입니다. 대화 밖에서 학생이 한 작업은 보이지 않으므로 추론하지 마세요.",
        "권장 레슨 초점이 아닌 역량을 에이전트가 한 줄로 설명한 경우에만 kind에 observed를 사용하세요.",
        f"기존 태그: {', '.join(tag['name'] for tag in input_data['tags'])}",
        f"입력: {_compact({'raw': input_data['raw'], 'open': input_data['open'], 'answer': input_data['answer']})}",
    ])


def _parse_array(text):
    trimmed = str(text or "").strip()
    try:
        parsed = json.loads(trimmed)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and isinstance(parsed.get("observations"), list):
            return parsed["observations"]
    except json.JSONDecodeError:
        pass
    start, end = trimmed.find("["), trimmed.rfind("]")
    if start >= 0 and end > start:
        return json.loads(trimmed[start:end + 1])
    raise ValueError("추출기 응답이 JSON 배열이 아닙니다")


def extract(input_data, payload):
    prompt = _extractor_prompt(input_data)
    env = {**os.environ, "DEVPROFILE_MODEL_CALL": "1"}
    command = os.environ.get("DEVPROFILE_EXTRACTOR_COMMAND")
    if command:
        result = subprocess.run(
            command, shell=True, input=prompt, text=True, capture_output=True,
            timeout=120, env=env, check=False,
        )
    else:
        host = os.environ.get("DEVPROFILE_HOST") or payload.get("host") or "claude"
        # 호스트 분기는 프롬프트를 argv로만 넘긴다. stdin으로도 같이 보내면 `claude -p`나
        # `codex exec`가 둘을 이어붙여 프롬프트가 두 번 들어갈 수 있고, 이 분기는 테스트에서
        # 스텁으로 대체되므로 그 사고가 영원히 드러나지 않는다.
        result = subprocess.run(
            headless_invocation(host, prompt), text=True, capture_output=True,
            timeout=120, env=env, check=False,
        )
    if result.returncode != 0:
        raise RuntimeError(f"추출기 종료 코드 {result.returncode}: {result.stderr or ''}")
    return [_validate_observation(candidate) for candidate in _parse_array(result.stdout)]


def _validate_observation(candidate):
    if not isinstance(candidate, dict) or not isinstance(candidate.get("comp"), list) or not candidate["comp"]:
        raise ValueError("관측 comp가 비어 있습니다")
    if not isinstance(candidate.get("kind"), list) or not candidate["kind"] or any(kind not in ACTIONS for kind in candidate["kind"]):
        raise ValueError("관측 kind에 행동 동사가 아닌 값이 있습니다")
    for tag in candidate["comp"]:
        if not isinstance(tag, str) or (tag not in AXES and not re.match(r"^[^/]+/[^/]+$", tag)):
            raise ValueError(f"역량 태그 깊이가 잘못되었습니다: {tag}")
    if not isinstance(candidate.get("text"), str) or not isinstance(candidate.get("src"), list):
        raise ValueError("관측 text 또는 src가 잘못되었습니다")
    return {
        "comp": list(dict.fromkeys(candidate["comp"])),
        "kind": list(candidate["kind"]),
        "text": candidate["text"],
        "status": "closed" if candidate.get("status") == "closed" else "open",
        "src": list(dict.fromkeys(candidate["src"])),
    }
