"""Tests unitarios para webhooks GitLab y Bitbucket (watchgate/api/routers/webhooks.py)."""

from __future__ import annotations

import hmac
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from watchgate.api.main import app


@pytest.fixture
def api_client():
    return TestClient(app)


def test_gitlab_webhook_success(api_client):
    secret = "secret_gitlab_token_123"
    headers = {
        "X-Gitlab-Event": "Merge Request Hook",
        "X-Gitlab-Token": secret,
    }
    payload = {
        "object_kind": "merge_request",
        "object_attributes": {"iid": 15, "action": "open"},
        "project": {"path_with_namespace": "group/project-repo"},
    }

    with patch.dict(os.environ, {"GITLAB_WEBHOOK_SECRET": secret}):
        response = api_client.post("/api/v1/webhooks/gitlab", headers=headers, json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["provider"] == "gitlab"
        assert data["pr_id"] == "15"
        assert data["repo"] == "group/project-repo"


def test_gitlab_webhook_unauthorized(api_client):
    secret = "secret_gitlab_token_123"
    headers = {
        "X-Gitlab-Event": "Merge Request Hook",
        "X-Gitlab-Token": "wrong_token",
    }
    payload = {"object_kind": "merge_request"}

    with patch.dict(os.environ, {"GITLAB_WEBHOOK_SECRET": secret}):
        response = api_client.post("/api/v1/webhooks/gitlab", headers=headers, json=payload)
        assert response.status_code == 401


def test_bitbucket_webhook_success(api_client):
    secret = "secret_bitbucket_key"
    body_bytes = (
        b'{"pullrequest": {"id": 42}, "repository": {"full_name": "workspace/bitbucket-repo"}}'
    )

    computed_sig = hmac.new(secret.encode("utf-8"), body_bytes, digestmod="sha256").hexdigest()
    headers = {
        "X-Event-Key": "pullrequest:created",
        "X-Hub-Signature": f"sha256={computed_sig}",
        "Content-Type": "application/json",
    }

    with patch.dict(os.environ, {"BITBUCKET_WEBHOOK_SECRET": secret}):
        response = api_client.post(
            "/api/v1/webhooks/bitbucket", content=body_bytes, headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["provider"] == "bitbucket"
        assert data["pr_id"] == "42"
        assert data["repo"] == "workspace/bitbucket-repo"
