from .decider import FORM_NAMES


def render_onboarding(profile):
    if profile.get("track") and profile.get("goal"):
        return ""
    return "\n".join([
        "[학습자 프로필 시작]",
        "첫 세션에는 자가평가 없이 두 가지만 물어보세요.",
        "1. 트랙은 AI / 풀스택 / 클라우드 중 무엇인가요?",
        "2. 이번 코호트에서 이루고 싶은 목표는 무엇인가요?",
        "답을 받은 다음 답변 첫 줄에 `[학습자 프로필 track=<트랙> goal=<목표>]`를 정확히 표시하세요. Stop 훅이 두 값만 저장합니다.",
    ])


def render_injection(decision, observations):
    if decision["form"] == "silent":
        return ""
    rules = "\n".join([
        "시범: 전부 수행하되 과정을 설명합니다.",
        "골격: 구조를 만들고 핵심 3~10줄만 빈칸으로 둡니다.",
        "설계→구현 분리: 코드 전에 설계를 한 번 묻고, 답한 설계 그대로 구현합니다.",
        "구현→검수 분리: 코드를 쓰지 말고 위치만 안내한 뒤 학생 구현을 검토합니다.",
        "강등은 설계 질문 1회 실패 시 골격, 빈칸 실패 시 시범으로 조용히 내립니다. 작업 중 승격하지 않습니다.",
    ])
    observation_slice = "\n".join(
        f"- {item['t1']} | {', '.join(item['comp'])} | {' → '.join(item['kind'])} | {item['text'][:100]}"
        for item in observations
    )
    output = "\n".join([
        f"[{FORM_NAMES[decision['form']]}]",
        f"레슨 초점: {decision['focus']}",
        f"개입 사유: {decision['rationale']}", "",
        "형태별 행동 규칙:", rules, "",
        "관련 관측 (태그 필터 → 최신순 → 상위 8개):",
        observation_slice or "- 관련 관측 없음", "",
        f"답변 첫 줄에 [{FORM_NAMES[decision['form']]}]와 위 개입 사유를 쓰고 관측 하나만 인용하세요. 다른 형태를 택하면 이유를 한 줄 덧붙이세요.",
    ])
    # DESIGN §7의 목표 주입량은 1,000~2,000자다. 10,000자는 Claude Code의 하드 상한이지
    # 목표가 아니다. 상한까지 채우면 프로필이 커질수록 주입이 커져 §7이 못 박은
    # "프로필이 300개든 2,400개든 주입량은 일정하다"가 깨진다.
    return output[:2000]


def render_profile(profile, observations):
    metrics = profile.get("metrics") or {}
    overrides = metrics.get("overrides", 0)
    transitions = metrics.get("autoSilenceTransitions", 0)
    lines = [
        "# 학습자 프로필", "", f"- 익명 ID: {profile['anonymousId']}",
        f"- 트랙: {profile.get('track') or '미설정'}", f"- 목표: {profile.get('goal') or '미설정'}",
        f"- 성공 지표 (우회 + 자동침묵전환): {overrides + transitions}",
        f"  - 우회: {overrides}", f"  - 자동침묵전환: {transitions}", "", "## 관측", "",
    ]
    if not observations:
        lines.append("아직 관측이 없습니다.")
    for observation in observations:
        lines.extend([
            f"- {observation['t1']} | {', '.join(observation['comp'])} | {' → '.join(observation['kind'])}",
            f"  {observation['text']}",
        ])
    return "\n".join(lines) + "\n"
