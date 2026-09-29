# Public pages update
- Routes: /features, /policies (140 policies, search + category filters), /how-it-works, landing (/) with Plans & Offers and collapsible "Browse all policies".
- Demo video: put your file at `frontend/public/PakSim-Walkthrough.mp4` (served as /PakSim-Walkthrough.mp4). Poster: `frontend/public/poster.svg`. If the file is missing, a poster fallback shows instead of a black box.
- Policies: edit `tools/generate_public_policies.py`, then run `python tools/generate_public_policies.py`. It rewrites both `backend/datasets/public_policies.json` (served at GET /api/public/policies) and `frontend/src/data/publicPolicies.json`. Every entry has a `kb_ref` that must exist in the approved knowledge-base manifest (checked by `backend/tests/test_public_policies.py`).
- Build: `cd frontend && npm install && npm run build`.
