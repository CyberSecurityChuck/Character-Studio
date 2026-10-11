"""Stand-in for the official CLIs in tests: same arguments and output shapes as Phase 2.5.

Usage: python fake_cli.py <claude|codex> <real CLI arguments...>
FAKE_CLI_MODE picks the behaviour; FAKE_CLI_LOG records arguments and environment.
"""

import json
import os
import sys
import time
from pathlib import Path

program, args = sys.argv[1], sys.argv[2:]
mode = os.environ.get("FAKE_CLI_MODE", "ok")
# Manual browser QA can switch behaviour between runs by editing this file.
mode_file = os.environ.get("FAKE_CLI_MODE_FILE")
if mode_file and os.path.isfile(mode_file):
    mode = Path(mode_file).read_text(encoding="utf-8").strip() or mode
log = os.environ.get("FAKE_CLI_LOG")
if log:
    with open(log, "a", encoding="utf-8") as file:
        leaked = sorted(
            key
            for key in os.environ
            if key.startswith(("CLAUDE", "ANTHROPIC")) or key in {"OPENAI_API_KEY", "CODEX_API_KEY"}
        )
        file.write(
            json.dumps(
                {
                    "program": program,
                    "args": args,
                    "cwd": os.getcwd(),
                    "leaked": leaked,
                    "stdin_closed": sys.stdin.read() == "",
                }
            )
            + "\n"
        )

analysis = json.loads(Path(os.environ["FAKE_CLI_ANALYSIS"]).read_text(encoding="utf-8"))

if args == ["--version"]:
    print("2.1.296 (Claude Code)" if program == "claude" else "codex-cli 0.162.1")
    sys.exit(0)
if args == ["auth", "status"]:
    print(
        json.dumps(
            {
                "loggedIn": mode != "signed_out",
                "authMethod": "claude.ai",
                "subscriptionType": "pro",
                "email": "private@example.com",
            }
        )
    )
    sys.exit(0)
if args == ["login", "status"]:
    print("Not logged in" if mode == "signed_out" else "Logged in using ChatGPT")
    sys.exit(0)

if mode == "slow":
    time.sleep(120)

if program == "claude":
    assert "-p" in args
    polishing = "--tools" in args and args[args.index("--tools") + 1] == ""
    if polishing and mode in ("ok", "drop"):
        instruction = args[args.index("-p") + 1]
        prompt = instruction.split("BEGIN PROMPT\n", 1)[1].split("\nEND PROMPT", 1)[0]
        polished = prompt.replace("Create one new photorealistic image", "Produce one new image")
        if mode == "drop":
            # A careless polish that loses Subject 1's identity instructions.
            polished = "\n".join(line for line in polished.splitlines() if "Subject 1" not in line)
        print(
            json.dumps({"is_error": False, "result": "", "structured_output": {"prompt": polished}})
        )
        sys.exit(0)
    if mode == "limit":
        envelope = {"is_error": True, "subtype": "error", "result": "You've hit your usage limit"}
    elif mode == "logged_out_run":
        envelope = {"is_error": True, "result": "Not logged in · Please run /login"}
    elif mode == "invalid":
        envelope = {"is_error": False, "result": "", "structured_output": {"schema_version": 1}}
    elif mode == "text":
        envelope = {"is_error": False, "result": "```json\n" + json.dumps(analysis) + "\n```"}
    else:
        envelope = {
            "is_error": False,
            "result": "",
            "structured_output": analysis,
            "total_cost_usd": 0.1,
        }
    print(json.dumps(envelope))
    sys.exit(1 if envelope["is_error"] else 0)

assert args[0] == "exec"
generating = "--output-schema" not in args
thread = f"fake-thread-{time.time_ns()}" if generating else "fake-thread"
print(json.dumps({"type": "thread.started", "thread_id": thread}), flush=True)
if mode == "limit":
    print(json.dumps({"type": "turn.failed", "error": {"message": "usage limit reached"}}))
    sys.exit(1)
output = Path(args[args.index("-o") + 1])
if generating:
    # Built-in image generation saves under <CODEX_HOME>/generated_images/<thread_id>/.
    from PIL import Image

    attached = [Path(args[i + 1]) for i, a in enumerate(args) if a == "-i"]
    assert attached and all(p.is_file() for p in attached), "attached images must exist"
    folder = Path(os.environ["CODEX_HOME"]) / "generated_images" / thread
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"exec-{time.time_ns()}.png"
    if mode == "outside":
        target = Path(os.environ["CODEX_HOME"]) / "elsewhere.png"
    if mode != "no_image":
        Image.new("RGB", (400, 300), "#c08060").save(target, "PNG")
    if mode == "save_then_hang":
        time.sleep(120)
    if mode == "no_image":
        message = "Built-in image generation isn't available in this session."
    elif mode == "silent":
        message = "Done."
    else:
        message = f"Saved the image to `{target}`"
    output.write_text(message, encoding="utf-8")
    print(json.dumps({"type": "turn.completed"}))
    sys.exit(0)
output.write_text(json.dumps(analysis) if mode != "invalid" else "{}", encoding="utf-8")
print(json.dumps({"type": "turn.completed"}))
