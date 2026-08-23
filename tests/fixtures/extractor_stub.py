#!/usr/bin/env python3
import os
import sys
from pathlib import Path


input_text = sys.stdin.read()
if os.environ.get("DEVPROFILE_STUB_INPUT_FILE"):
    Path(os.environ["DEVPROFILE_STUB_INPUT_FILE"]).write_text(input_text, encoding="utf-8")
if os.environ.get("DEVPROFILE_STUB_FAIL") == "1":
    raise SystemExit(17)
sys.stdout.write(os.environ.get("DEVPROFILE_STUB_OUTPUT", "[]"))
