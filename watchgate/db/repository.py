"""Funciones auxiliares CRUD y repositorio para WatchGate."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from watchgate.core.models import AggregatedResult
from watchgate.db.models import (
    PRScore,
    SemanticCache,
    User,
    UserAPIKey,
    UserTokenUsage,
)

_TOKEN_PREFIX_LIVE = "wg_live_"
_TOKEN_PREFIX_TEST = "wg_test_"


def hash_token(raw_token: str) -> str:
    """Calcula el hash SHA-256 en hexadecimal de un token crudo."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_api_key(is_test: bool = False) -> tuple[str, str, str]:
    """Genera una clave de API nueva.

    Retorna: (raw_token, key_prefix, key_hash)
    El raw_token solo se muestra una vez al usuario y NUNCA se guarda en BD.
    """
    prefix = _TOKEN_PREFIX_TEST if is_test else _TOKEN_PREFIX_LIVE
    raw_secret = secrets.token_hex(32)
    raw_token = f"{prefix}{raw_secret}"
    key_prefix = raw_token[:12]  # "wg_live_1234"
    key_hash = hash_token(raw_token)
    return raw_token, key_prefix, key_hash


def create_user(
    session: Session,
    email: str,
    name: str,
    role: str = "revisor",
    custom_llm_api_key: str | None = None,
) -> User:
    """Crea o recupera un usuario de la plataforma."""
    stmt = select(User).where(User.email == email)
    existing = session.exec(stmt).first()
    if existing:
        return existing

    user = User(
        id=str(uuid.uuid4()),
        email=email,
        name=name,
        role=role,
        custom_llm_api_key=custom_llm_api_key,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def create_api_key(
    session: Session,
    user_id: str,
    name: str = "Default Key",
    scopes: str = "analysis:write,scores:read",
    is_test: bool = False,
) -> tuple[UserAPIKey, str]:
    """Crea una nueva API Key para el usuario.

    Retorna: (UserAPIKey_guardada_en_bd, raw_token_crudo_para_el_usuario)
    """
    raw_token, key_prefix, key_hash = generate_api_key(is_test=is_test)

    api_key = UserAPIKey(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes=scopes,
    )
    session.add(api_key)
    session.commit()
    session.refresh(api_key)
    return api_key, raw_token


def verify_api_key(session: Session, raw_token: str) -> tuple[UserAPIKey, User] | None:
    """Verifica un token crudo y retorna (UserAPIKey, User) si es válido, o None."""
    if not raw_token or not (
        raw_token.startswith(_TOKEN_PREFIX_LIVE) or raw_token.startswith(_TOKEN_PREFIX_TEST)
    ):
        return None

    target_hash = hash_token(raw_token)
    stmt = select(UserAPIKey).where(UserAPIKey.key_hash == target_hash)
    key_record = session.exec(stmt).first()

    if not key_record:
        return None

    # Comprobar expiración si está configurada
    if key_record.expires_at and key_record.expires_at < datetime.now(UTC):
        return None

    stmt_user = select(User).where(User.id == key_record.user_id)
    user = session.exec(stmt_user).first()
    if not user:
        return None

    # Actualizar marca de último uso
    key_record.last_used_at = datetime.now(UTC)
    session.add(key_record)
    session.commit()

    return key_record, user


def record_token_usage(
    session: Session, user_id: str, tokens_used: int, month: str | None = None
) -> UserTokenUsage:
    """Registra o incrementa el consumo de tokens mensual para un usuario."""
    month_key = month or datetime.now(UTC).strftime("%Y-%m")
    stmt = select(UserTokenUsage).where(
        UserTokenUsage.user_id == user_id, UserTokenUsage.month == month_key
    )
    usage = session.exec(stmt).first()

    if not usage:
        usage = UserTokenUsage(user_id=user_id, month=month_key, tokens_used=tokens_used)
    else:
        usage.tokens_used += tokens_used

    session.add(usage)
    session.commit()
    session.refresh(usage)
    return usage


def get_token_usage(session: Session, user_id: str, month: str | None = None) -> int:
    """Obtiene los tokens consumidos por el usuario en el mes especificado."""
    month_key = month or datetime.now(UTC).strftime("%Y-%m")
    stmt = select(UserTokenUsage).where(
        UserTokenUsage.user_id == user_id, UserTokenUsage.month == month_key
    )
    usage = session.exec(stmt).first()
    return usage.tokens_used if usage else 0


def save_pr_score(
    session: Session,
    aggregated_result: AggregatedResult,
    user_id: str | None = None,
) -> PRScore:
    """Guarda un resultado de análisis de PR en el histórico pr_scores."""
    layer_json = {
        k: v.model_dump() for k, v in aggregated_result.layer_results.items()
    }
    score_record = PRScore(
        id=str(uuid.uuid4()),
        repo=aggregated_result.repo,
        pr_id=aggregated_result.pr_id,
        user_id=user_id,
        score=aggregated_result.score,
        semaforo=aggregated_result.semaforo.value,
        layer_results_json=str(layer_json),
        weights_used_json=str(aggregated_result.weights_used),
    )
    session.add(score_record)
    session.commit()
    session.refresh(score_record)
    return score_record


def get_semantic_cache(session: Session, diff_hash_value: str) -> str | None:
    """Recupera la respuesta JSON en caché de la capa semántica."""
    stmt = select(SemanticCache).where(SemanticCache.diff_hash == diff_hash_value)
    cached = session.exec(stmt).first()
    return cached.output_json if cached else None


def set_semantic_cache(session: Session, diff_hash_value: str, output_json: str) -> SemanticCache:
    """Guarda una respuesta JSON en la caché semántica."""
    stmt = select(SemanticCache).where(SemanticCache.diff_hash == diff_hash_value)
    existing = session.exec(stmt).first()

    if existing:
        existing.output_json = output_json
        existing.created_at = datetime.now(UTC)
        cache_record = existing
    else:
        cache_record = SemanticCache(diff_hash=diff_hash_value, output_json=output_json)

    session.add(cache_record)
    session.commit()
    session.refresh(cache_record)
    return cache_record
