"""Decision actors: a real Responses API adapter and a repeatable offline substitute."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Protocol


ACTION_NAMES = ("read_material", "check_rules", "query_slots", "save_draft", "request_confirmation", "block", "finish")


class DecisionActor(Protocol):
    def choose(self, state: dict[str, Any]) -> dict[str, str]: ...


class OfflineActor:
    """Deterministic fallback for tests and demos; it is not evidence of LLM quality."""
    def choose(self, state: dict[str, Any]) -> dict[str, str]:
        if not state.get("material_read"):
            return {"action": "read_material", "reason": "Need metadata before review."}
        if not state.get("material_result", {}).get("found"):
            return {"action": "block", "reason": "The requested material does not exist, so it cannot be reviewed."}
        if not state.get("rule_result"):
            return {"action": "check_rules", "reason": "Need rule evidence before scheduling."}
        rules = state["rule_result"]
        if rules["missing_fields"]:
            return {"action": "block", "reason": "Required metadata is missing."}
        if rules["violations"]:
            return {"action": "block", "reason": "High-risk rule violation requires remediation."}
        if not state.get("slot_result"):
            return {"action": "query_slots", "reason": "Material passed; check requested time."}
        slots = state["slot_result"]
        if not slots["available"] and not state["request"].get("confirm_alternative"):
            return {"action": "request_confirmation", "reason": "Requested hard time is occupied; an alternative needs user confirmation."}
        if not state.get("save_result"):
            return {"action": "save_draft", "reason": "The requested or user-confirmed time can now be drafted."}
        return {"action": "finish", "reason": "Save outcome has been observed."}


class OpenAIResponsesActor:
    """Uses the official Responses API with constrained JSON output, not agent-side hidden reasoning."""
    def __init__(self) -> None:
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.model = os.environ.get("OPENAI_MODEL")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        if not self.api_key or not self.model:
            raise ValueError("OPENAI_API_KEY and OPENAI_MODEL are required for --mode openai")

    def choose(self, state: dict[str, Any]) -> dict[str, str]:
        instructions = (
            "You are a scheduling decision maker. Return ONLY JSON with action and reason. "
            f"action must be one of {list(ACTION_NAMES)}. Decide the next action from the supplied state. "
            "Never select publication. If a requested hard slot is occupied and no confirmation exists, "
            "select request_confirmation rather than save_draft. Block missing metadata or rule violations."
        )
        payload = {"model": self.model, "instructions": instructions, "input": json.dumps(state, ensure_ascii=False), "store": False}
        req = urllib.request.Request(
            f"{self.base_url}/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"model_http_{exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"model_network_error: {exc.reason}") from exc
        text = body.get("output_text") or _extract_output_text(body)
        try:
            decision = json.loads(text.strip().removeprefix("```json").removesuffix("```").strip())
        except json.JSONDecodeError as exc:
            raise RuntimeError("model_returned_non_json_action") from exc
        if decision.get("action") not in ACTION_NAMES or not isinstance(decision.get("reason"), str):
            raise RuntimeError("model_returned_invalid_action")
        return {"action": decision["action"], "reason": decision["reason"]}


def _extract_output_text(body: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in body.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                chunks.append(content.get("text", ""))
    return "".join(chunks)
