import json
import os
import subprocess
import sys
from pathlib import Path


def configured_form_url():
    if os.environ.get("DEVPROFILE_FORM_URL"):
        return os.environ["DEVPROFILE_FORM_URL"]
    config = json.loads((Path(__file__).resolve().parent.parent / "config.json").read_text(encoding="utf-8"))
    return config.get("formUrl")


def create_draft(target, body):
    absolute = Path(target).resolve()
    with absolute.open("x", encoding="utf-8") as stream:
        stream.write(body)
    return absolute


def _copy_to_clipboard(text):
    if sys.platform == "darwin":
        commands = [["pbcopy"]]
    elif sys.platform == "win32":
        commands = [["clip"]]
    else:
        commands = [["wl-copy"], ["xclip", "-selection", "clipboard"]]
    for command in commands:
        try:
            result = subprocess.run(command, input=text, text=True, capture_output=True, check=False)
            if result.returncode == 0:
                return
        except OSError:
            pass
    raise RuntimeError("클립보드 복사에 실패했습니다.")


def _open_form(url):
    command = ["open", url] if sys.platform == "darwin" else ["cmd", "/c", "start", "", url] if sys.platform == "win32" else ["xdg-open", url]
    try:
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except OSError as error:
        raise RuntimeError("폼 URL을 열지 못했습니다.") from error
    if result.returncode != 0:
        raise RuntimeError("폼 URL을 열지 못했습니다.")


def approve_draft(target):
    url = configured_form_url()
    if not url:
        raise RuntimeError("폼 URL이 설정되지 않았습니다. 배포자에게 문의하세요.")
    body = Path(target).resolve().read_text(encoding="utf-8")
    _copy_to_clipboard(body)
    _open_form(url)
    return body
