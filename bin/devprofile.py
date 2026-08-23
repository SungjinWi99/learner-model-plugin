#!/usr/bin/env python3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.renderer import render_profile
from src.repository import read_observations, read_profile
from src.submission import approve_draft, create_draft


def _option(name):
    try:
        return sys.argv[sys.argv.index(name) + 1]
    except (ValueError, IndexError):
        return None


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else None
    rendered = render_profile(read_profile(), read_observations())
    if command == "profile":
        sys.stdout.write(rendered)
        return
    if command == "submit" and "--draft" in sys.argv:
        target = _option("--draft")
        if not target:
            raise ValueError("--draft 뒤에 제출 사본 경로가 필요합니다.")
        absolute = create_draft(target, rendered)
        sys.stdout.write(f"제출 사본을 만들었습니다: {absolute}\n원하지 않는 관측을 이 사본에서 지운 뒤 --approve로 확인하세요.\n")
        return
    if command == "submit" and "--approve" in sys.argv:
        draft = _option("--approve")
        if not draft:
            raise ValueError("--approve 뒤에 검토를 마친 제출 사본 경로가 필요합니다.")
        body = approve_draft(draft)
        sys.stdout.write(f"최종 제출 사본:\n\n{body}\n")
        sys.stdout.write("제출 사본을 클립보드에 복사하고 폼을 열었습니다. 붙여넣은 뒤 학생이 직접 제출하세요.\n")
        return
    raise ValueError("사용법: devprofile <profile|submit --draft <경로>|submit --approve <경로>>")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        sys.stderr.write(f"{error}\n")
        raise SystemExit(1)
