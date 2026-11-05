from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent import SchedulingAgent
from .decision import OfflineActor, OpenAIResponsesActor
from .tools import LocalTools


def main() -> int:
    parser = argparse.ArgumentParser(description="Review material and save only a scheduling draft.")
    parser.add_argument("--request", required=True, type=Path, help="Path to request JSON")
    parser.add_argument("--mode", choices=("offline", "openai"), default="offline")
    parser.add_argument("--state-path", type=Path, help="Draft-state JSON path (default: .runtime/drafts.json)")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--output", type=Path, help="Optional output JSON file")
    parser.add_argument("--trace-output", type=Path, help="Optional trace-only JSON file")
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    actor = OfflineActor() if args.mode == "offline" else OpenAIResponsesActor()
    result = SchedulingAgent(LocalTools(state_path=args.state_path), actor, args.max_steps).run(request)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if args.trace_output:
        args.trace_output.parent.mkdir(parents=True, exist_ok=True)
        args.trace_output.write_text(json.dumps(result["trace"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if result["status"] in {"draft_saved", "needs_confirmation", "blocked", "save_failed", "incomplete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
