"""Strict, lexical scope checks with no network or filesystem resolution."""

import posixpath
from urllib.parse import urlsplit, urlunsplit

from .models import AssessmentRequest


class ScopeViolation(ValueError):
    """Raised when a candidate leaves the user-supplied boundary."""


def _canonical_url(value: str) -> tuple[str, str, int | None, str, str]:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ScopeViolation(f"unsupported or incomplete URL: {value!r}")
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    canonical = urlunsplit((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        parsed.query,
        "",
    ))
    normalized = urlsplit(canonical)
    return (
        normalized.scheme,
        normalized.hostname or "",
        normalized.port,
        normalized.path,
        normalized.query,
    )


def _path_is_within(candidate: str, allowed: str) -> bool:
    base = allowed.rstrip("/") or "/"
    return candidate == base or base == "/" or candidate.startswith(base + "/")


def assert_external_target(request: AssessmentRequest, candidate: str) -> None:
    candidate_url = _canonical_url(candidate)
    for allowed in request.external_targets:
        allowed_url = _canonical_url(allowed)
        if request.report_directed and candidate_url == allowed_url:
            return
        if request.report_directed:
            continue
        same_origin = candidate_url[:3] == allowed_url[:3]
        if same_origin and _path_is_within(candidate_url[3], allowed_url[3]):
            return
    raise ScopeViolation(f"external target is outside the frozen scope: {candidate}")


def _canonical_posix_path(value: str) -> str:
    if not value.startswith("/") or "\x00" in value:
        raise ScopeViolation(f"internal path must be absolute: {value!r}")
    if ".." in value.split("/"):
        raise ScopeViolation(f"parent traversal is not allowed: {value!r}")
    return posixpath.normpath(value)


def assert_internal_path(request: AssessmentRequest, candidate: str) -> None:
    candidate_path = _canonical_posix_path(candidate)
    for allowed in request.internal_paths:
        allowed_path = _canonical_posix_path(allowed)
        if _path_is_within(candidate_path, allowed_path):
            return
    raise ScopeViolation(f"internal path is outside the frozen scope: {candidate}")
