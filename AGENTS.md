# 교육용 에이전트 플러그인

코딩 에이전트 위에 얹혀, 학생의 개발 경험을 영속적으로 기억하고 그 기억에 따라
에이전트의 개입 형태를 조절하는 계층. 부트캠프 코호트 단위로 배포한다.

설계는 `docs/DESIGN.md`, 용어는 `CONTEXT.md`, 되돌리기 비싼 결정은 `docs/adr/`에 있다.

## 코드와 테스트

Python 3. **런타임은 표준 라이브러리만** 쓴다 — 학생 설치에 pip이 끼면 안 된다.

테스트는 `uv run --with pytest python -m pytest -q`. 기본 `python3`에는 pytest가 없다.

**seam은 훅 프로세스 하나뿐이다** (stdin 페이로드 → stdout + 저장소 파일).
관측 검색기·개입 결정기·프로필 저장소를 따로 유닛 테스트하지 않는다. 이유는 이슈 #1의 Testing Decisions에 있다.

## Agent skills

### Issue tracker

GitHub Issues (`gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

기본 5개 라벨을 그대로 사용한다. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context (`CONTEXT.md` + `docs/adr/`). See `docs/agents/domain.md`.
