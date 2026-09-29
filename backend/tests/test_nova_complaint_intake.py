"""Nova chat complaint intake: complaints are saved only after the mobile number is verified."""
import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp()) / "intake.db"
shutil.copy(Path(__file__).parents[1] / "supportnova.db", _TMP)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

ISSUE = "Phone par 'No Service', 'SIM not detected' dikh raha hai"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _say(client, headers, text, session=None):
    form = {"text": text}
    if session:
        form["session_id"] = session
    r = client.post("/api/nova/assistant/message", data=form, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


class _Result(list):
    total = 0


def _complaints(client, headers):
    data = client.get("/api/complaints", params={"page_size": 5}, headers=headers).json()
    out = _Result(data["items"])
    out.total = data["total"]
    return out


def test_customer_without_sim_cannot_register_complaint(client):
    r = client.post("/api/auth/register", json={"email": "nosim@test.pk", "password": "Test#12345", "full_name": "No Sim"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    res = _say(client, headers, ISSUE)
    assert "registered nahi" in res["reply"]
    assert not res["data"].get("complaint_code")
    assert _complaints(client, headers) == []
    form = client.post("/api/complaints", json={"title": "abc", "description": "abcdef"}, headers=headers)
    assert form.status_code == 403


def test_number_is_asked_then_verified_and_complaint_saved(client):
    headers = _login(client, "customer@supportnova.demo", "Customer#12345")
    before = _complaints(client, headers).total
    first = _say(client, headers, ISSUE)
    assert "mobile number" in first["reply"].lower()
    assert first["data"].get("awaiting_mobile")
    assert _complaints(client, headers).total == before  # nothing saved yet
    sid = first["session_id"]

    unknown = _say(client, headers, "03451112223", sid)
    assert "registered nahi" in unknown["reply"]
    assert _complaints(client, headers).total == before

    ok = _say(client, headers, "0300-1234567", sid)
    code = ok["data"].get("complaint_code")
    assert code and code in ok["reply"]
    items = _complaints(client, headers)
    assert items.total == before + 1
    assert items[0]["code"] == code  # newest first


def test_number_of_another_customer_is_rejected(client):
    r = client.post("/api/auth/register", json={"email": "other@test.pk", "password": "Test#12345", "full_name": "Other"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # give this new account its own SIM through the DB so it passes the "has a SIM" check
    from app.database import SessionLocal
    from app.models import SimCard, User
    with SessionLocal() as db:
        uid = db.query(User).filter(User.email == "other@test.pk").first().id
        db.add(SimCard(sim_number="8992200000000000999", phone_number="03451234567", customer_id=uid, status="ACTIVE"))
        db.commit()
    first = _say(client, headers, ISSUE)
    res = _say(client, headers, "03001234567", first["session_id"])  # belongs to the demo customer
    assert "linked nahi" in res["reply"]
    assert _complaints(client, headers) == []
    res = _say(client, headers, "03451234567", first["session_id"])
    assert res["data"].get("complaint_code")
    assert len(_complaints(client, headers)) == 1


def test_cancel_and_topic_change_do_not_save(client):
    headers = _login(client, "customer@supportnova.demo", "Customer#12345")
    before = _complaints(client, headers).total
    first = _say(client, headers, "Recharge ke baad balance show nahi ho raha")
    assert first["data"].get("awaiting_mobile")
    res = _say(client, headers, "cancel", first["session_id"])
    assert "register nahi" in res["reply"]
    assert _complaints(client, headers).total == before
