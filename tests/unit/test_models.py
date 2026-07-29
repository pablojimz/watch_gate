"""Tests de watchgate/core/models.py (spec §1)."""

import json

import pytest
from pydantic import ValidationError

from watchgate.core.models import (
    AggregatedResult,
    CommitAuthor,
    Confidence,
    FileChange,
    FileStatus,
    LayerResult,
    NormalizedDiff,
    ReputationMetadata,
    RiskCategory,
    Semaforo,
)


def _sample_diff() -> NormalizedDiff:
    return NormalizedDiff(
        base_sha="a" * 40,
        head_sha="b" * 40,
        repo_path="/tmp/repo",
        files=[
            FileChange(
                path="src/app.py",
                status=FileStatus.MODIFIED,
                diff_hunk="@@ -1,1 +1,2 @@\n+import os\n",
                additions=1,
                deletions=0,
            )
        ],
        commit_messages=["fix: cosa"],
        authors=[CommitAuthor(name="Ana", email="ana@example.com", login="ana")],
    )


def test_normalized_diff_roundtrip():
    diff = _sample_diff()
    assert diff.files[0].status == FileStatus.MODIFIED
    assert json.loads(diff.model_dump_json())["repo_path"] == "/tmp/repo"


def test_file_change_renamed_allows_old_path():
    fc = FileChange(
        path="new.py",
        old_path="old.py",
        status=FileStatus.RENAMED,
        diff_hunk="",
        additions=0,
        deletions=0,
    )
    assert fc.old_path == "old.py"


@pytest.mark.parametrize("risk_score", [-1, 101])
def test_layer_result_risk_score_bounds(risk_score):
    with pytest.raises(ValidationError):
        LayerResult(layer_name="static", risk_score=risk_score, justification="x")


def test_layer_result_defaults():
    result = LayerResult(layer_name="static", risk_score=0, justification="sin hallazgos")
    assert result.skipped is False
    assert result.category is None
    assert result.confidence is None
    assert result.tool_calls_made == 0


def test_layer_result_semantic_fields():
    result = LayerResult(
        layer_name="semantic",
        risk_score=85,
        justification="llamada de red no declarada",
        category=RiskCategory.EXFILTRACION,
        confidence=Confidence.ALTA,
        tool_calls_made=2,
    )
    assert result.category == RiskCategory.EXFILTRACION
    assert result.tool_calls_made == 2


def test_aggregated_result_is_the_single_json_contract():
    """AggregatedResult.model_dump_json() debe ser el contrato único (§1)."""
    layer_results = {
        "static": LayerResult(layer_name="static", risk_score=20, justification="ok"),
        "dependencies": LayerResult(layer_name="dependencies", risk_score=10, justification="ok"),
        "reputation": LayerResult(layer_name="reputation", risk_score=40, justification="ok"),
        "semantic": LayerResult(
            layer_name="semantic",
            risk_score=85,
            justification="llamada de red no declarada",
            category=RiskCategory.EXFILTRACION,
            confidence=Confidence.ALTA,
        ),
    }
    aggregated = AggregatedResult(
        score=47,
        semaforo=Semaforo.AMARILLO,
        layer_results=layer_results,
        weights_used={"static": 0.25, "dependencies": 0.20, "reputation": 0.15, "semantic": 0.40},
        pr_id="123",
        repo="owner/repo",
        timestamp="2026-07-29T00:00:00Z",
    )
    payload = json.loads(aggregated.model_dump_json())
    assert payload["score"] == 47
    assert payload["semaforo"] == "amarillo"
    assert payload["layer_results"]["semantic"]["risk_score"] == 85
    # Round-trip: lo que produce el modelo es válido para reconstruirlo.
    assert AggregatedResult.model_validate(payload) == aggregated


def test_reputation_metadata_optional_fields():
    meta = ReputationMetadata(
        author_login=None,
        author_account_age_days=None,
        author_prior_contributions_to_repo=0,
        commit_email_matches_verified_email=False,
        commit_is_signed=False,
        signing_key_seen_before_for_login=None,
        repo_has_history_of_signed_commits=True,
    )
    assert meta.author_login is None
    assert meta.signing_key_seen_before_for_login is None
