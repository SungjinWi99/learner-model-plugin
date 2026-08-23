[에이전트가 설치할 때 따를 절차서](docs/INSTALL_FOR_AGENT.md)

# DevProfile

DevProfile은 코딩 에이전트 위에 얹혀 학생의 실제 개발 관측을 기억하고, 새 작업에서 학생과 에이전트가 맡을 인지적 일을 조절하는 플러그인입니다. Claude Code와 Codex CLI가 `~/.devprofile/` 하나를 공유하므로 프로젝트나 도구를 바꿔도 학습자 프로필이 이어집니다.

프롬프트, 파일 쓰기, 답변 종료를 먼저 raw로 남긴 뒤 관측을 추출합니다. 파일 쓰기에서는 경로와 변경 줄 수만 저장하고 코드 본문은 저장하지 않습니다. 프롬프트 원문과 잘린 답변 말미는 정제된 뒤 7일이 지나면 폐기합니다. 추출이 실패한 raw는 다음 세션에서 다시 회수합니다.

관측이 관련된 작업에서만 `[설계→구현 분리]` 같은 개입 형태와 한 줄의 개입 사유가 나타납니다. 사소한 일은 조용히 처리하고, `그냥 해줘`라고 우회하면 즉시 물러납니다. 세 번 연속 우회하면 여유가 자동으로 없음으로 바뀌지만 관측은 계속 쌓입니다.

구현은 **호스트 어댑터 → 프로필 저장소 → 이벤트 기록기 → 관측 추출기 → 관측 검색기 → 개입 결정기 → 렌더러** 한 방향으로 흐릅니다. 추출과 UserPromptSubmit의 역량 태깅만 호스트의 headless CLI를 사용하며, 검색과 숙련도 계산과 개입 결정은 코드로 결정론적으로 처리합니다.

모델을 부르는 곳은 이 둘뿐이고, 둘 다 환경변수로 바꿔치기할 수 있습니다 — `DEVPROFILE_EXTRACTOR_COMMAND`와 `DEVPROFILE_TAGGER_COMMAND`. 테스트는 이 두 지점에만 스텁을 꽂습니다. 태깅은 `UserPromptSubmit` 안에서 돌기 때문에 10초 예산을 두고, 넘기거나 실패하면 키워드 매칭으로 떨어집니다. 태깅이 실패해도 학생의 프롬프트는 막히지 않고, 꺼내오는 관측이 줄어들 뿐입니다.

## 프로필 열람과 제출

설치된 호스트 대화에서는 `/devprofile profile`로 프로필을 보고 `/devprofile submit draft`로 현재 프로젝트에 검토용 제출 사본을 만들 수 있습니다. 사본을 편집한 뒤 훅이 안내하는 `/devprofile submit approve <사본 경로>`를 학생이 직접 입력해야만 클립보드 복사와 폼 열기가 일어납니다.

저장소를 직접 다루는 배포자는 같은 기능을 아래 CLI로 확인할 수 있습니다.

```sh
python3 bin/devprofile.py profile
python3 bin/devprofile.py submit --draft ./devprofile-submission.md
```

두 번째 명령이 만든 사본에서 빼고 싶은 관측을 지울 수 있습니다. 원본 학습자 프로필은 바뀌지 않습니다. 검토가 끝난 사본만 다음 명령으로 명시적으로 승인합니다.

```sh
python3 bin/devprofile.py submit --approve ./devprofile-submission.md
```

승인하면 익명 ID와 트랙이 포함된 사본을 클립보드에 복사하고 폼 URL을 엽니다. 플러그인이 폼을 대신 제출하지는 않습니다. 코호트 배포자는 [config.json](config.json)의 `formUrl`을 설정해야 하며, 로컬 확인에서는 `DEVPROFILE_FORM_URL` 환경변수로 덮어쓸 수 있습니다.

## 데이터 위치

기본 위치는 `~/.devprofile/`입니다. 테스트와 격리 실행에서는 `DEVPROFILE_ROOT`로 바꿀 수 있습니다. 학습자 프로필은 학생이 승인하지 않는 한 강사나 플러그인 개발자에게 자동으로 전송되지 않습니다.
