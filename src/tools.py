"""Local, deterministic business tools. They intentionally never publish content."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


class LocalTools:
    def __init__(self, data_dir: Path | None = None, state_path: Path | None = None):
        self.data_dir = data_dir or ROOT / "data"
        self.state_path = state_path or ROOT / ".runtime" / "drafts.json"
        self.materials = self._load("materials.json")["materials"]
        self.rules = self._load("rules.json")
        self.slots = self._load("schedule.json")["slots"]

    def _load(self, name: str) -> Any:
        return json.loads((self.data_dir / name).read_text(encoding="utf-8"))

    def read_material(self, material_id: str) -> dict[str, Any]:
        item = next((m for m in self.materials if m["id"] == material_id), None)
        if not item:
            return {"found": False, "material_id": material_id, "error": "material_not_found"}
        return {"found": True, "material": deepcopy(item)}

    def check_rules(self, material: dict[str, Any]) -> dict[str, Any]:
        missing = [field for field in self.rules["required_fields"] if not material.get(field)]
        violations = []
        searchable = " ".join(str(material.get(k, "")) for k in ("title", "caption", "tags")).lower()
        for forbidden in self.rules["forbidden_terms"]:
            if forbidden.lower() in searchable:
                violations.append({"rule": "forbidden_term", "term": forbidden, "severity": "high"})
        if material.get("rights_status") != "cleared":
            violations.append({"rule": "rights_not_cleared", "severity": "high"})
        return {
            "passed": not missing and not violations,
            "missing_fields": missing,
            "violations": violations,
            "risk_level": "high" if violations else ("medium" if missing else "none"),
        }

    def query_slots(self, desired_slot: str) -> dict[str, Any]:
        target = next((x for x in self.slots if x["time"] == desired_slot), None)
        available = [x["time"] for x in self.slots if x["status"] == "available"]
        return {
            "desired_slot": desired_slot,
            "available": bool(target and target["status"] == "available"),
            "occupant": target.get("occupant") if target and target["status"] == "occupied" else None,
            "alternatives": available,
        }

    def save_draft(self, draft: dict[str, Any]) -> dict[str, Any]:
        """Idempotently save one draft; failure injection exists solely for verification."""
        if draft.get("simulate_save_failure"):
            return {"saved": False, "status": "failed", "error": "simulated_storage_unavailable"}
        state = self._read_state()
        existing = next((x for x in state["drafts"] if x["idempotency_key"] == draft["idempotency_key"]), None)
        if existing:
            return {"saved": True, "status": "duplicate", "draft_id": existing["draft_id"]}
        draft_id = f"draft-{len(state['drafts']) + 1:03d}"
        saved = {"draft_id": draft_id, **deepcopy(draft)}
        state["drafts"].append(saved)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"saved": True, "status": "saved", "draft_id": draft_id}

    def _read_state(self) -> dict[str, list[dict[str, Any]]]:
        if not self.state_path.exists():
            return {"drafts": []}
        return json.loads(self.state_path.read_text(encoding="utf-8"))
