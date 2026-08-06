"""Extracción de primitivas git puras (spec §2).

Convierte `(repo_path, base_sha, head_sha)` o un parche en texto plano (`diff_text`)
en un `NormalizedDiff`.
No hace ninguna llamada de red: todo se resuelve en local o en memoria.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import git
import unidiff

from watchgate.core.models import CommitAuthor, FileChange, FileStatus, NormalizedDiff

if TYPE_CHECKING:
    from git import Repo
    from git.diff import Diff

logger = logging.getLogger("watchgate.diffparser")

# Mapeo extensión -> lenguaje. Deliberadamente acotado a lo que las capas
# estática/dependencias necesitan reconocer (spec §4, §5); una extensión no
# listada da language=None, no un error.
_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".sh": "shell",
    ".bash": "shell",
    ".rb": "ruby",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
}

# Ficheros especiales sin extensión (o con extensión no significativa) que
# las capas necesitan reconocer igualmente por su nombre exacto.
_FILENAME_TO_LANGUAGE: dict[str, str] = {
    "Dockerfile": "dockerfile",
    "Makefile": "makefile",
    "PKGBUILD": "shell",
}


def _infer_language(path: str) -> str | None:
    """Infiere el lenguaje de un fichero a partir de su nombre/extensión.

    Devuelve None si no se reconoce — no es un error, simplemente significa
    que ninguna capa tiene reglas específicas para ese tipo de fichero.
    """
    filename = path.rsplit("/", 1)[-1]
    if filename in _FILENAME_TO_LANGUAGE:
        return _FILENAME_TO_LANGUAGE[filename]
    suffix_idx = filename.rfind(".")
    if suffix_idx == -1:
        return None
    ext = filename[suffix_idx:]
    return _EXTENSION_TO_LANGUAGE.get(ext)


def _status_from_diff_item(diff_item: Diff) -> FileStatus:
    """Determina el FileStatus a partir de las banderas booleanas del objeto
    Diff de GitPython (`new_file`/`deleted_file`/`renamed_file`), que son más
    fiables que `change_type` (este último llega a `None` en varios casos,
    p.ej. archivos borrados en algunas versiones de GitPython).

    `change_type` como "R100"/"R87" (renombrado con % de similitud) se usa
    como respaldo adicional por si `renamed_file` no está disponible.
    """
    if diff_item.new_file:
        return FileStatus.ADDED
    if diff_item.deleted_file:
        return FileStatus.DELETED
    if getattr(diff_item, "renamed_file", False) or (
        diff_item.change_type and diff_item.change_type.startswith("R")
    ):
        return FileStatus.RENAMED
    return FileStatus.MODIFIED


def _count_additions_deletions(patch_text: str) -> tuple[int, int]:
    additions = 0
    deletions = 0
    in_hunk = False
    for line in patch_text.splitlines():
        if line.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return additions, deletions


def _extract_file_changes(repo: Repo, base_sha: str, head_sha: str) -> list[FileChange]:
    base_commit = repo.commit(base_sha)
    head_commit = repo.commit(head_sha)
    diff_index = base_commit.diff(head_commit, create_patch=True)

    changes: list[FileChange] = []
    for diff_item in diff_index:
        status = _status_from_diff_item(diff_item)
        path = diff_item.b_path or diff_item.a_path
        old_path = (
            diff_item.a_path
            if status is FileStatus.RENAMED and diff_item.a_path != diff_item.b_path
            else None
        )

        raw_diff = diff_item.diff
        raw: bytes
        if raw_diff is None:
            raw = b""
        elif isinstance(raw_diff, bytes):
            raw = raw_diff
        else:
            raw = raw_diff.encode("utf-8")
        is_binary = False
        patch_text = ""
        if raw:
            try:
                patch_text = raw.decode("utf-8")
            except UnicodeDecodeError:
                is_binary = True
                patch_text = ""
            else:
                # git emite este marcador textual (decodificable en UTF-8)
                # en vez de un patch real cuando detecta contenido binario.
                if patch_text.startswith("Binary files "):
                    is_binary = True
                    patch_text = ""

        additions, deletions = (0, 0) if is_binary else _count_additions_deletions(patch_text)

        changes.append(
            FileChange(
                path=path or "",
                old_path=old_path,
                status=status,
                diff_hunk=patch_text,
                additions=additions,
                deletions=deletions,
                is_binary=is_binary,
                language=_infer_language(path or ""),
            )
        )
    return changes


def _decode_message(message: str | bytes) -> str:
    """`Commit.message` de GitPython es `str | bytes` según su firma de tipos
    (bytes si el mensaje no es UTF-8 válido); lo normalizamos siempre a str."""
    if isinstance(message, bytes):
        return message.decode("utf-8", errors="replace")
    return message


def _extract_commit_messages(repo: Repo, base_sha: str, head_sha: str) -> list[str]:
    if base_sha == head_sha:
        return []
    commits = list(repo.iter_commits(f"{base_sha}..{head_sha}", first_parent=True))
    return [_decode_message(c.message).strip() for c in commits]


def _extract_authors(repo: Repo, base_sha: str, head_sha: str) -> list[CommitAuthor]:
    if base_sha == head_sha:
        return []
    commits = list(repo.iter_commits(f"{base_sha}..{head_sha}", first_parent=True))
    seen_emails: set[str] = set()
    authors: list[CommitAuthor] = []
    for c in commits:
        email = c.author.email or ""
        if email in seen_emails:
            continue
        seen_emails.add(email)
        authors.append(CommitAuthor(name=c.author.name or "", email=email))
    return authors


def parse_diff(repo_path: str, base_sha: str, head_sha: str) -> NormalizedDiff:
    """Punto de entrada único de la Línea 1 para repositorios Git en disco local.

    No lanza excepción en el caso de diff vacío (`base_sha == head_sha`):
    simplemente devuelve un NormalizedDiff con listas vacías.
    """
    repo = git.Repo(repo_path)
    files = _extract_file_changes(repo, base_sha, head_sha)
    commit_messages = _extract_commit_messages(repo, base_sha, head_sha)
    authors = _extract_authors(repo, base_sha, head_sha)
    return NormalizedDiff(
        base_sha=base_sha,
        head_sha=head_sha,
        repo_path=repo_path,
        files=files,
        commit_messages=commit_messages,
        authors=authors,
    )


def parse_diff_from_text(
    diff_text: str,
    base_sha: str = "0000000",
    head_sha: str = "0000000",
    repo_path: str = ".",
    commit_messages: list[str] | None = None,
    authors: list[CommitAuthor] | None = None,
) -> NormalizedDiff:
    """Parsea un parche de texto unificado usando unidiff en memoria sin requerir un repo en disco.

    Soporta la ingesta de diffs en texto plano enviados vía HTTP por la Engine API SaaS.
    """
    if not diff_text or not diff_text.strip():
        return NormalizedDiff(
            base_sha=base_sha,
            head_sha=head_sha,
            repo_path=repo_path,
            files=[],
            commit_messages=commit_messages or [],
            authors=authors or [],
        )

    file_changes: list[FileChange] = []
    try:
        patch_set = unidiff.PatchSet.from_string(diff_text)
        for patched_file in patch_set:
            path = patched_file.path
            old_path: str | None = None

            if patched_file.is_added_file:
                status = FileStatus.ADDED
            elif patched_file.is_removed_file:
                status = FileStatus.DELETED
            elif patched_file.is_rename:
                status = FileStatus.RENAMED
                old_path = patched_file.source_file
            else:
                status = FileStatus.MODIFIED

            diff_hunk_str = str(patched_file)
            additions = patched_file.added
            deletions = patched_file.removed
            is_binary = getattr(patched_file, "is_binary_file", False)

            file_changes.append(
                FileChange(
                    path=path,
                    old_path=old_path,
                    status=status,
                    diff_hunk=diff_hunk_str,
                    additions=additions,
                    deletions=deletions,
                    is_binary=is_binary,
                    language=_infer_language(path),
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error parseando diff_text con unidiff (%r). Se retorna diff plano.", exc)

    return NormalizedDiff(
        base_sha=base_sha,
        head_sha=head_sha,
        repo_path=repo_path,
        files=file_changes,
        commit_messages=commit_messages or [],
        authors=authors or [],
    )
