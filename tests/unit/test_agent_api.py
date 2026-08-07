"""Tests unitarios e integrados para la API de Agentes de IA (watchgate/api/routers/agent.py)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from watchgate.api.dependencies import get_db_session
from watchgate.api.main import app
from watchgate.db.repository import create_api_key, create_organization, create_user


@pytest.fixture
def test_db_session(tmp_path):
    db_file = tmp_path / "test_agent_api.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session, engine


@pytest.fixture
def api_client(test_db_session):
    session, _engine = test_db_session

    app.dependency_overrides[get_db_session] = lambda: session
    client = TestClient(app)
    yield client, session
    app.dependency_overrides.clear()


def test_agent_precheck_fast_mode(api_client):
    client, session = api_client
    org = create_organization(session, name="Agent Org")
    user = create_user(session, email="agent@corp.com", name="Agent User", org_id=org.id)
    _, raw_token = create_api_key(
        session, user_id=user.id, org_id=org.id, default_agent_name="opencode-bot"
    )

    diff_text = """diff --git a/app.py b/app.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/app.py
@@ -0,0 +1,1 @@
+x = 42
"""

    headers = {"Authorization": f"Bearer {raw_token}"}
    payload = {
        "diff_text": diff_text,
        "base_sha": "abc1234",
        "head_sha": "def5678",
        "metadata": {"pr_id": "100", "repo": "acme/agent-app"},
    }

    response = client.post("/api/v1/agent/precheck", headers=headers, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "score" in data
    assert "semaforo" in data
    # La capa semántica debe estar deshabilitada en precheck
    assert data["layer_results"]["semantic"]["skipped"] is True


def test_agent_analyze_with_guidance(api_client):
    client, session = api_client
    org = create_organization(session, name="Agent Org 2")
    user = create_user(session, email="bot@corp.com", name="Bot User", org_id=org.id)
    _, raw_token = create_api_key(session, user_id=user.id, org_id=org.id)

    diff_text = """diff --git a/app.py b/app.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/app.py
@@ -0,0 +1,1 @@
+print('secure code')
"""

    headers = {"Authorization": f"Bearer {raw_token}"}
    payload = {
        "diff_text": diff_text,
        "base_sha": "0000000",
        "head_sha": "1111111",
        "metadata": {"pr_id": "200", "repo": "acme/bot-repo"},
    }

    response = client.post("/api/v1/agent/analyze", headers=headers, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "analysis" in data
    assert "guidance" in data

    guidance = data["guidance"]
    assert "is_mergeable" in guidance
    assert guidance["recommended_action"] in ("PROCEED", "RETRY_WITH_FIX", "BLOCK_HUMAN_REVIEW")
    assert "summary_for_agent" in guidance


def test_agent_verify_fix(api_client):
    client, session = api_client
    org = create_organization(session, name="Agent Org 3")
    user = create_user(session, email="fixer@corp.com", name="Fixer", org_id=org.id)
    _, raw_token = create_api_key(session, user_id=user.id, org_id=org.id)

    orig_diff = """diff --git a/package.json b/package.json
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/package.json
@@ -0,0 +1,5 @@
+{
+  "dependencies": {
+    "lodash": "4.17.11"
+  }
+}
"""

    cand_diff = """diff --git a/package.json b/package.json
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/package.json
@@ -0,0 +1,5 @@
+{
+  "dependencies": {
+    "lodash": "^4.17.21"
+  }
+}
"""

    headers = {"Authorization": f"Bearer {raw_token}"}
    payload = {
        "original_diff": orig_diff,
        "candidate_diff": cand_diff,
        "base_sha": "0000000",
        "head_sha": "1111111",
    }

    response = client.post("/api/v1/agent/verify-fix", headers=headers, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "risk_reduced" in data
    assert "previous_score" in data
    assert "new_score" in data
    assert data["previous_score"] >= data["new_score"]
    assert data["risk_reduced"] is True
    assert len(data["resolved_findings"]) > 0


def test_agent_policy_endpoint(api_client):
    client, session = api_client
    org = create_organization(
        session, name="Policy Org", monthly_token_quota=500_000
    )
    user = create_user(session, email="pol@corp.com", name="Policy User", org_id=org.id)
    _, raw_token = create_api_key(session, user_id=user.id, org_id=org.id)

    headers = {"Authorization": f"Bearer {raw_token}"}
    response = client.get("/api/v1/agent/policy", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["org_id"] == org.id
    assert data["monthly_token_quota"] == 500_000
    assert data["quota_remaining"] == 500_000
    assert "thresholds" in data
    assert "weights" in data
