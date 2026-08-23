import re


FORM_NAMES = {
    "silent": "침묵 대행", "demonstration": "시범", "skeleton": "골격",
    "design_split": "설계→구현 분리", "implementation_review": "구현→검수 분리",
}


def _is_trivial(prompt):
    return bool(re.search(r"(?:오타|typo|리네임|rename|이름\s*변경|포맷|format|정렬만|주석만)", str(prompt or ""), re.I))


def _proficiency(observations):
    if not observations:
        return "middle"
    kinds = [kind for observation in observations for kind in observation["kind"]]
    implemented = kinds.count("implemented")
    stuck = sum(kind in {"stuck", "overrode"} for kind in kinds)
    asked = kinds.count("asked")
    if stuck > len(kinds) / 2:
        return "bottom"
    if stuck > 0:
        return "low"
    if implemented >= 5 and asked == 0:
        return "ceiling"
    if implemented >= 2 and asked == 0:
        return "high"
    return "middle"


def _form_for(proficiency):
    return {
        "bottom": "demonstration", "low": "skeleton", "middle": "design_split",
        "high": "implementation_review", "ceiling": "silent",
    }[proficiency]


def decide(prompt, tags, observations, slack, recent_interventions=None, reason_counts=None):
    recent_interventions = recent_interventions or []
    reason_counts = reason_counts or {}
    if _is_trivial(prompt):
        return {"form": "silent", "reason": "trivial", "rationale": "", "focus": None, "observation": None}
    if not tags:
        return {"form": "silent", "reason": "no_tags", "rationale": "", "focus": None, "observation": None}
    if slack == "none":
        return {"form": "silent", "reason": "no_slack", "rationale": "", "focus": tags[0], "observation": None}
    recent = set(recent_interventions[-2:])
    ranked = []
    for index, tag in enumerate(tags):
        relevant = [observation for observation in observations if tag in observation["comp"]]
        band = _proficiency(relevant)
        value = {"bottom": 1, "low": 4, "middle": 5, "high": 3, "ceiling": 0}[band] - (1 if tag in recent else 0)
        ranked.append({"tag": tag, "index": index, "relevant": relevant, "proficiency": band, "value": value})
    focus = sorted(ranked, key=lambda item: (-item["value"], item["index"]))[0]
    observation = next((item for item in focus["relevant"] if reason_counts.get(item["id"], 0) < 2), None)
    form = _form_for(focus["proficiency"])
    return {
        "form": form,
        "reason": "proficiency_ceiling" if form == "silent" else "intervention",
        "focus": focus["tag"], "observation": observation,
        "rationale": f"관측 “{observation['text'][:140]}”에 근거했습니다." if observation else "아직 관련 관측이 없어 기본 개입을 권장합니다.",
    }
