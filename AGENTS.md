# 교육용 에이전트 플러그인

코딩 에이전트 위에 얹혀, 학생의 개발 경험을 영속적으로 기억하고 그 기억에 따라
에이전트의 개입 형태를 조절하는 계층. 부트캠프 코호트 단위로 배포한다.

설계는 `docs/DESIGN.md`, 용어는 `CONTEXT.md`, 되돌리기 비싼 결정은 `docs/adr/`에 있다.

## 코드

Python 3. **런타임은 표준 라이브러리만 쓴다** — 학생이 설치할 때 pip이 필요하면 안 된다.

계층은 한 방향으로 흐른다. 아래 모듈은 위를 모른다.

```
호스트 어댑터 → 저장소 → 기록기 → 추출기 → 검색기 → 결정기 → 렌더러
```

모델을 부르는 곳은 **추출기와 태거 둘뿐**이고, 둘 다 환경변수로 교체 가능하다
(`DEVPROFILE_EXTRACTOR_COMMAND`, `DEVPROFILE_TAGGER_COMMAND`). 검색·숙련도 계산·개입 결정은
전부 코드가 결정론적으로 한다.

**훅은 학생의 프롬프트를 절대 막지 않는다.** 어떤 실패든 삼키고 종료 코드 0으로 나간다.
저장소가 깨져 주입이 사라져도 마찬가지다. 이탈이 불완전한 프로필보다 나쁘기 때문에
받아들인 부작용이다(`docs/DESIGN.md` §1).

## 테스트

기본 `python3`에는 pytest가 없다. 둘 중 하나로 돌린다.

```sh
uv run --with pytest python -m pytest -q
pip install pytest && python3 -m pytest -q
```

**seam은 훅 프로세스 하나뿐이다.** stdin 페이로드 → stdout 주입 + 저장소 파일.
검색기·결정기·저장소를 따로 유닛 테스트하지 않는다 — seam이 늘면 구현을 테스트하게 되고,
내부를 재구성할 때마다 테스트가 깨진다(이슈 #1 Testing Decisions).
추출기와 태거만 스텁으로 치환하며, 테스트에서 실제 모델을 부르지 않는다.

## Agent skills

### Issue tracker

GitHub Issues (`gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

기본 5개 라벨을 그대로 사용한다. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context (`CONTEXT.md` + `docs/adr/`). See `docs/agents/domain.md`.
