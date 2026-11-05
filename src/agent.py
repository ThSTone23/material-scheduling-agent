"""Bounded ReAct-style tool loop with business safety guards."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .decision import DecisionActor
from .tools import LocalTools


class SchedulingAgent:
    def __init__(self, tools: LocalTools, actor: DecisionActor, max_steps: int = 8):
        self.tools, self.actor, self.max_steps = tools, actor, max_steps

    def run(self, request: dict[str, Any]) -> dict[str, Any]:
        required = {"request_id", "material_id", "requested_slot"}
        missing = sorted(required - request.keys())
        if missing:
            return self._result(request, "blocked", "NEEDS_INFO", [f"missing_request_fields:{','.join(missing)}"], None, [], {"status": "not_attempted"})
        state: dict[str, Any] = {"request": deepcopy(request), "material_read": False}
        trace: list[dict[str, Any]] = []
        risk_reasons: list[str] = []
        for step in range(1, self.max_steps + 1):
            try:
                choice = self.actor.choose(self._public_state(state))
            except RuntimeError as exc:
                trace.append(self._event(step, "model", {}, {"error": str(exc)}, "block", "Model decision could not be obtained."))
                return self._result(request, "blocked", "MODEL_ERROR", [str(exc)], None, trace, {"status": "not_attempted"})
            action, reason = choice["action"], choice["reason"]
            unsafe_reason = self._unsafe_action_reason(action, state)
            if unsafe_reason:
                trace.append(self._event(step, "safety_guard", {"model_action": action}, {"error": unsafe_reason}, "return_model_error", reason))
                return self._result(request, "blocked", "MODEL_ERROR", [unsafe_reason], self._suggested_slot(state), trace, {"status": "not_attempted"})
            event = self._perform(step, action, reason, state, risk_reasons)
            trace.append(event)
            if action == "block":
                return self._result(request, "blocked", "BLOCKED", risk_reasons or [reason], self._suggested_slot(state), trace, {"status": "not_attempted"})
            if action == "request_confirmation":
                return self._result(request, "needs_confirmation", "PENDING_CONFIRMATION", risk_reasons, self._suggested_slot(state), trace, {"status": "not_attempted"})
            if action == "finish":
                save = state.get("save_result", {"status": "not_attempted"})
                final = "draft_saved" if save.get("saved") else "save_failed"
                review = "APPROVED" if save.get("saved") else "SAVE_FAILED"
                return self._result(request, final, review, risk_reasons, self._suggested_slot(state), trace, save)
        trace.append(self._event(self.max_steps, "limit", {}, {"max_steps": self.max_steps}, "incomplete", "Configured action limit reached."))
        return self._result(request, "incomplete", "STEP_LIMIT_REACHED", risk_reasons + ["max_steps_reached"], self._suggested_slot(state), trace, state.get("save_result", {"status": "not_attempted"}))

    def _perform(self, step: int, action: str, reason: str, state: dict[str, Any], risks: list[str]) -> dict[str, Any]:
        request = state["request"]
        if action == "read_material":
            result = self.tools.read_material(request["material_id"])
            state["material_read"] = True
            state["material_result"] = result
            if not result["found"]:
                risks.append(result["error"])
            return self._event(step, "read_material", {"material_id": request["material_id"]}, _summary(result), "next_model_action", reason)
        if action == "check_rules":
            material_result = state.get("material_result", {})
            if not material_result.get("found"):
                risks.append("cannot_check_rules_without_material")
                return self._event(step, action, {}, {"error": "no_material"}, "block", reason)
            result = self.tools.check_rules(material_result["material"])
            state["rule_result"] = result
            risks.extend([f"missing:{x}" for x in result["missing_fields"]])
            risks.extend([f"rule:{x['rule']}" for x in result["violations"]])
            return self._event(step, action, {"material_id": request["material_id"]}, _summary(result), "next_model_action", reason)
        if action == "query_slots":
            result = self.tools.query_slots(request["requested_slot"])
            state["slot_result"] = result
            if not result["available"]:
                risks.append("requested_slot_occupied")
            return self._event(step, action, {"desired_slot": request["requested_slot"]}, _summary(result), "next_model_action", reason)
        if action == "save_draft":
            allowed, slot, error = self._save_guard(state)
            if not allowed:
                risks.append(error)
                return self._event(step, action, {"requested_slot": request["requested_slot"]}, {"saved": False, "error": error}, "request_confirmation", "Safety guard prevented unconfirmed hard-time change.")
            material = state["material_result"]["material"]
            result = self.tools.save_draft({
                "idempotency_key": request["request_id"], "material_id": request["material_id"], "scheduled_slot": slot,
                "simulate_save_failure": bool(material.get("simulate_save_failure")),
            })
            state["save_result"] = result
            return self._event(step, action, {"idempotency_key": request["request_id"], "scheduled_slot": slot}, _summary(result), "finish", reason)
        if action == "request_confirmation":
            return self._event(step, action, {"requested_slot": request["requested_slot"]}, {"alternatives": state.get("slot_result", {}).get("alternatives", [])}, "return_pending_confirmation", reason)
        if action == "block":
            return self._event(step, action, {}, {"risk_reasons": risks}, "return_blocked", reason)
        return self._event(step, "finish", {}, {"save_status": state.get("save_result", {}).get("status")}, "return_final", reason)

    def _save_guard(self, state: dict[str, Any]) -> tuple[bool, str | None, str]:
        slots = state.get("slot_result")
        if not slots:
            return False, None, "slot_not_checked"
        if slots["available"]:
            return True, state["request"]["requested_slot"], ""
        if state["request"].get("confirm_alternative") and slots["alternatives"]:
            return True, slots["alternatives"][0], ""
        return False, None, "hard_time_change_not_confirmed"

    @staticmethod
    def _unsafe_action_reason(action: str, state: dict[str, Any]) -> str | None:
        """Model output is advisory; lifecycle order is enforced outside the model."""
        if action == "read_material" and state.get("material_read"):
            return "material_already_read"
        if action == "check_rules" and (not state.get("material_result", {}).get("found") or state.get("rule_result")):
            return "rule_check_precondition_failed"
        if action == "query_slots":
            rules = state.get("rule_result")
            if not rules or not rules.get("passed") or state.get("slot_result"):
                return "slot_query_precondition_failed"
        if action == "save_draft":
            rules = state.get("rule_result")
            if not rules or not rules.get("passed") or not state.get("slot_result"):
                return "save_precondition_failed"
        if action == "request_confirmation":
            if not state.get("slot_result") or state["slot_result"].get("available") or state["request"].get("confirm_alternative"):
                return "confirmation_precondition_failed"
        if action == "finish" and not state.get("save_result"):
            return "finish_precondition_failed"
        return None

    @staticmethod
    def _public_state(state: dict[str, Any]) -> dict[str, Any]:
        public = {k: v for k, v in state.items() if k != "save_result" or v is not None}
        public["allowed_actions"] = SchedulingAgent._allowed_actions(state)
        return public

    @staticmethod
    def _allowed_actions(state: dict[str, Any]) -> list[str]:
        """A workflow skeleton; the model still decides from tool-returned business state."""
        if not state.get("material_read"):
            return ["read_material", "block"]
        if not state.get("material_result", {}).get("found"):
            return ["block"]
        if not state.get("rule_result"):
            return ["check_rules", "block"]
        rules = state["rule_result"]
        if not rules.get("passed"):
            return ["block"]
        if not state.get("slot_result"):
            return ["query_slots", "block"]
        slots = state["slot_result"]
        if not slots["available"] and not state["request"].get("confirm_alternative"):
            return ["request_confirmation", "block"]
        if not state.get("save_result"):
            return ["save_draft", "block"]
        return ["finish"]

    @staticmethod
    def _event(step: int, tool: str, params: dict[str, Any], summary: dict[str, Any], next_action: str, reason: str) -> dict[str, Any]:
        return {"step": step, "tool": tool, "parameters": params, "result_summary": summary, "next_action": next_action, "decision_basis": reason}

    @staticmethod
    def _suggested_slot(state: dict[str, Any]) -> str | None:
        slots = state.get("slot_result")
        if not slots:
            return None
        return state["request"]["requested_slot"] if slots["available"] else (slots["alternatives"][0] if slots["alternatives"] else None)

    @staticmethod
    def _result(request: dict[str, Any], status: str, review: str, risks: list[str], suggested: str | None, trace: list[dict[str, Any]], save: dict[str, Any]) -> dict[str, Any]:
        return {"request_id": request.get("request_id"), "material_id": request.get("material_id"), "status": status, "review_status": review, "risk_reasons": risks, "suggested_slot": suggested, "pending_confirmation": status == "needs_confirmation", "draft_save": save, "trace": trace, "published": False}


def _summary(value: dict[str, Any]) -> dict[str, Any]:
    """Trace enough observable facts without copying full input metadata."""
    keys = ("found", "passed", "missing_fields", "violations", "risk_level", "available", "occupant", "alternatives", "saved", "status", "draft_id", "error")
    return {k: value[k] for k in keys if k in value}
