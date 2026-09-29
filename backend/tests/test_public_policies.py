"""Public policy catalogue must stay consistent with the approved knowledge base."""
import json
from pathlib import Path

DS = Path(__file__).resolve().parents[1] / "datasets"


def test_public_policies_reference_approved_kb():
    pub = json.loads((DS / "public_policies.json").read_text(encoding="utf-8"))
    kb = json.loads((DS / "knowledge_base" / "manifest.json").read_text(encoding="utf-8"))
    kb_ids = {d.get("policy_id") or d.get("code") for d in kb["documents"]}
    assert pub["count"] >= 120 and pub["count"] == len(pub["policies"])
    ids = [p["id"] for p in pub["policies"]]
    assert len(ids) == len(set(ids))
    for p in pub["policies"]:
        assert p["kb_ref"] in kb_ids, p
