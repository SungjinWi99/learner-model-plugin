# 에이전트 설치 절차서

이 절차는 사람이 명령을 옮겨 적게 하지 말고, 현재 대화를 수행하는 코딩 에이전트가 직접 실행한다. 설치 전에 Python 3가 있는지 확인하고, 설치 뒤에는 반드시 실제 호스트를 한 번 실행해 훅 주입까지 검증한다.

## 1. 호스트 감지와 분기

먼저 아래 명령으로 현재 호스트를 확인한다.

```sh
command -v codex
command -v claude
python3 --version
```

현재 대화가 Codex라면 Codex 분기로, Claude Code라면 Claude 분기로 간다. 둘 다 설치되어 있어도 현재 호스트 하나를 먼저 검증하고, 학생이 둘 다 쓸 때만 다른 분기도 설치한다.

## 2. 설치 명령

### Codex CLI

```sh
codex plugin marketplace add SungjinWi99/learner-model-plugin
codex plugin add devprofile@devprofile
```

### Claude Code

```sh
claude plugin marketplace add SungjinWi99/learner-model-plugin
claude plugin install devprofile@devprofile
```

코호트 배포자는 설치 전에 저장소의 `config.json`에 해당 코호트의 `formUrl`을 넣는다. URL이 없어도 프로필 열람과 제출 사본 편집은 동작하지만, 최종 승인 제출은 눈에 띄는 오류로 중단된다.

## 3. 자체 검증

목록에 보이는지만 확인하지 않는다. 임시 데이터 루트에서 더미 프롬프트를 실제 호스트에 보내고 답변 첫 줄에 개입 형태가 나타나는지 확인한다.

### Codex CLI 검증

```sh
verify_root="$(mktemp -d)"
DEVPROFILE_ROOT="$verify_root" codex exec --skip-git-repo-check '테스트 전략을 추가하는 작업입니다. 주입된 지시를 따르고 답변 첫 줄의 대괄호 개입 형태만 출력하세요.' | tee /tmp/devprofile-codex-check.txt
grep -E '^\[(시범|골격|설계→구현 분리|구현→검수 분리)\]' /tmp/devprofile-codex-check.txt
grep -R '"e":"inject"' "$verify_root/raw"
```

`grep`이 성공하고 `$verify_root/raw/`에 JSONL 파일이 생겨야 설치가 끝난 것이다.

Codex에서 `grep`이 실패하거나 raw 파일이 없다면 가장 먼저 `/hooks`를 열어 이 프로젝트의 DevProfile 훅을 사용자가 직접 신뢰 승인하게 한다. 에이전트는 이 승인을 대신할 수 없다. 승인 뒤 같은 검증을 다시 실행한다. 이 승인이 남아 있으면 플러그인은 설치돼도 조용히 실행되지 않으며, 이것이 유일한 조용한 실패 지점이다. 이 검증을 생략하면 “설치했지만 안 쓴 학생”과 “승인이 안 돼 못 쓴 학생”을 구분할 수 없다.

### Claude Code 검증

```sh
verify_root="$(mktemp -d)"
DEVPROFILE_ROOT="$verify_root" claude -p '테스트 전략을 추가하는 작업입니다. 주입된 지시를 따르고 답변 첫 줄의 대괄호 개입 형태만 출력하세요.' | tee /tmp/devprofile-claude-check.txt
grep -E '^\[(시범|골격|설계→구현 분리|구현→검수 분리)\]' /tmp/devprofile-claude-check.txt
grep -R '"e":"inject"' "$verify_root/raw"
```

`grep`이 성공하고 `$verify_root/raw/`에 JSONL 파일이 생겨야 설치가 끝난 것이다. 실패하면 `claude plugin list`와 훅 오류 출력을 확인하고 수정한 뒤 다시 더미 프롬프트를 실행한다.

## 4. 첫 세션 확인

새 세션을 시작해 트랙(AI / 풀스택 / 클라우드)과 목표 두 가지만 묻는지 확인한다. 자가평가나 숙련도 입력을 요구하면 안 된다. 에이전트 답변 첫 줄의 `[학습자 프로필 track=... goal=...]` 표시를 Stop 훅이 읽어 두 값을 저장한다. 마지막으로 학생이 `/devprofile profile`을 입력해 트랙, 목표, 랜덤 익명 ID가 보이는지 확인한다.
