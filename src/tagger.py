import json
import os
import subprocess

from .host_adapter import headless_invocation


def _parse_tags(text, allowed):
    trimmed = str(text or "").strip()
    parsed = json.loads(trimmed[trimmed.index("["):trimmed.rindex("]") + 1])
    if not isinstance(parsed, list):
        raise ValueError("태그 배열이 아닙니다")
    return list(dict.fromkeys(tag for tag in parsed if tag in allowed))


def _keyword_tags(prompt, tags):
    normalized = str(prompt or "").lower()
    return [
        tag["name"] for tag in tags
        if tag["name"].lower() in normalized
        or any(part.lower() in normalized for part in tag["name"].split("/"))
    ]


def tag_prompt(prompt, tags, host):
    allowed = [tag["name"] for tag in tags]
    try:
        request = "\n".join([
            "다음 작업에 직접 관련된 역량 태그만 JSON 문자열 배열로 반환하세요.",
            f"허용 태그: {', '.join(allowed)}", f"작업: {prompt}",
        ])
        command = os.environ.get("DEVPROFILE_TAGGER_COMMAND")
        try:
            timeout_ms = float(os.environ.get("DEVPROFILE_TAGGER_TIMEOUT_MS", "10000"))
        except ValueError:
            timeout_ms = 10000
        timeout = min(timeout_ms if timeout_ms else 10000, 10000) / 1000
        env = {**os.environ, "DEVPROFILE_MODEL_CALL": "1"}
        result = subprocess.run(
            command if command else headless_invocation(host, request),
            shell=bool(command), input=request, text=True, capture_output=True,
            timeout=timeout, env=env, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("태깅 실패")
        return _parse_tags(result.stdout, allowed)
    except Exception:
        return _keyword_tags(prompt, tags)
