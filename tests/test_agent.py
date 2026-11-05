import json
import tempfile
import unittest
from pathlib import Path

from src.agent import SchedulingAgent
from src.decision import OfflineActor
from src.tools import LocalTools


ROOT = Path(__file__).resolve().parents[1]


def request(name: str):
    return json.loads((ROOT / "examples" / "inputs" / name).read_text(encoding="utf-8"))


class SchedulingAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.agent = SchedulingAgent(LocalTools(state_path=Path(self.temp.name) / "drafts.json"), OfflineActor())

    def tearDown(self):
        self.temp.cleanup()

    def test_normal_material_creates_a_draft_never_publication(self):
        result = self.agent.run(request("normal.json"))
        self.assertEqual(result["status"], "draft_saved")
        self.assertEqual(result["draft_save"]["status"], "saved")
        self.assertFalse(result["published"])

    def test_missing_metadata_is_blocked_before_slot_query(self):
        result = self.agent.run(request("missing_info.json"))
        self.assertEqual(result["status"], "blocked")
        self.assertIn("missing:caption", result["risk_reasons"])
        self.assertNotIn("query_slots", [x["tool"] for x in result["trace"]])

    def test_unknown_material_is_blocked_after_reading_result(self):
        result = self.agent.run({"request_id": "req-unknown", "material_id": "NOPE", "requested_slot": "2026-11-06T19:00"})
        self.assertEqual(result["status"], "blocked")
        self.assertIn("material_not_found", result["risk_reasons"])

    def test_rule_risk_is_blocked(self):
        result = self.agent.run(request("rule_risk.json"))
        self.assertEqual(result["review_status"], "BLOCKED")
        self.assertIn("rule:forbidden_term", result["risk_reasons"])

    def test_conflict_offers_alternative_and_requires_confirmation(self):
        result = self.agent.run(request("conflict.json"))
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertEqual(result["suggested_slot"], "2026-11-06T19:00")
        self.assertEqual(result["draft_save"]["status"], "not_attempted")

    def test_confirmed_alternative_can_be_saved(self):
        result = self.agent.run(request("conflict_confirmed.json"))
        self.assertEqual(result["status"], "draft_saved")
        self.assertEqual(result["suggested_slot"], "2026-11-06T19:00")

    def test_duplicate_request_creates_one_draft(self):
        first = self.agent.run(request("duplicate.json"))
        second = self.agent.run(request("duplicate.json"))
        self.assertEqual(first["draft_save"]["status"], "saved")
        self.assertEqual(second["draft_save"]["status"], "duplicate")
        state = json.loads((Path(self.temp.name) / "drafts.json").read_text(encoding="utf-8"))
        self.assertEqual(len(state["drafts"]), 1)

    def test_save_failure_is_exposed(self):
        result = self.agent.run(request("save_failure.json"))
        self.assertEqual(result["status"], "save_failed")
        self.assertEqual(result["draft_save"]["status"], "failed")

    def test_step_limit_returns_explicit_incomplete(self):
        limited = SchedulingAgent(LocalTools(state_path=Path(self.temp.name) / "limited.json"), OfflineActor(), max_steps=1)
        result = limited.run(request("normal.json"))
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["review_status"], "STEP_LIMIT_REACHED")

    def test_unsafe_model_save_action_is_blocked_before_any_save(self):
        class UnsafeActor:
            def choose(self, state):
                return {"action": "save_draft", "reason": "unsafe test action"}
        result = SchedulingAgent(LocalTools(state_path=Path(self.temp.name) / "unsafe.json"), UnsafeActor()).run(request("normal.json"))
        self.assertEqual(result["review_status"], "MODEL_ERROR")
        self.assertEqual(result["risk_reasons"], ["save_precondition_failed"])
