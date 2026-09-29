from pathlib import Path
import json


def test_bundled_knowledge_base_manifest_has_at_least_20_documents():
    manifest = Path(__file__).parents[1] / "datasets" / "knowledge_base" / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert len(data.get("documents", [])) >= 20


def test_submission_roles_are_seeded_in_source():
    seed = (Path(__file__).parents[1] / "app" / "seed.py").read_text(encoding="utf-8")
    assert '"reviewer@supportnova.demo"' in seed
    assert '"manager@supportnova.demo"' in seed
