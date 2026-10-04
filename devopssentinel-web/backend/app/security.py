"""Security helpers: redaction, input validation, origin checks.

Every value that leaves the backend passes through :func:`redact_text`.
The Bash engine already redacts, but defense-in-depth keeps a second,
independent guard so a future engine change cannot leak a secret.
"""

from __future__ import annotations

import json
import re

# Kubernetes DNS-1123 names (contexts allow a few extra characters).
_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9._-]{0,251}[a-z0-9])?$")
_CONTEXT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,252}$")
_KIND_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,62}$")
# Incident/evidence identifiers may contain upper case (e.g. INC12345).
_INCIDENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

# Line-level redaction. Conservative: when a line looks sensitive we drop
# the sensitive remainder rather than trying to preserve it verbatim.
_REDACT_LINE = re.compile(
    r"(authorization|bearer|token|password|passwd|client_secret|access_key|"
    r"secret_access_key|session_token|private_key|apikey|api_key|"
    r"-----begin [a-z ]*private key-----|xoxb-|xoxp-|ghp_|github_pat_|glpat-|eyj)",
    re.IGNORECASE,
)
_URL_CRED = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")
_KV_CRED = re.compile(
    r"(?i)\b(password|passwd|pwd|token|secret|apikey|api_key|client_secret)\b\s*[=:]\s*(\"[^\"]*\"|'[^']*'|\S+)"
)
_BEARER = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?")
_KNOWN_PREFIX = re.compile(r"\b(ghp_[A-Za-z0-9]{10,}|github_pat_[A-Za-z0-9_]{10,}|glpat-[A-Za-z0-9_-]{10,}|xox[bp]-[A-Za-z0-9-]{10,})")

REDACTED = "[REDACTED]"


def _looks_like_json(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def _redact_value(value: str) -> str:
    """Redact a single unstructured string (used for JSON string values)."""
    value = _URL_CRED.sub(r"\1[REDACTED]@", value)
    value = _KV_CRED.sub(lambda m: f"{m.group(1)}={REDACTED}", value)
    value = _BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", value)
    value = _JWT.sub(REDACTED, value)
    value = _KNOWN_PREFIX.sub(REDACTED, value)
    if _REDACT_LINE.search(value):
        value = REDACTED
    return value


def _redact_json_document(text: str) -> str | None:
    """Redact a whole JSON document without breaking its structure.

    The engine's ``--json`` mode is pretty-printed, so a line-at-a-time sweep
    would replace structural lines (for example a capability string that merely
    mentions ``TOKEN``) and leave unparseable JSON behind. Parsing first keeps
    the machine-readable contract intact while still removing credentials.
    Returns ``None`` when the text is not a single valid JSON document.
    """
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None

    def walk(node: object) -> object:
        if isinstance(node, str):
            return _redact_value(node)
        if isinstance(node, list):
            return [walk(item) for item in node]
        if isinstance(node, dict):
            return {key: walk(value) for key, value in node.items()}
        return node

    return json.dumps(walk(payload), ensure_ascii=False, indent=2)


def redact_text(text: str) -> str:
    """Redact credentials, tokens and private keys from arbitrary text.

    Structured (JSON) lines are redacted token-by-token so the payload stays
    parseable; unstructured lines that look sensitive are dropped wholesale.
    """
    if not text:
        return text
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        redacted = _redact_json_document(text)
        if redacted is not None:
            return redacted
    out_lines: list[str] = []
    in_pem = False
    for line in text.splitlines():
        low = line.lower()
        if "-----begin" in low and "private key-----" in low:
            in_pem = True
            out_lines.append("[REDACTED PRIVATE KEY]")
            continue
        if in_pem:
            if "-----end" in low and "private key-----" in low:
                in_pem = False
            continue
        line = _URL_CRED.sub(r"\1[REDACTED]@", line)
        line = _KV_CRED.sub(lambda m: f"{m.group(1)}={REDACTED}", line)
        line = _BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", line)
        line = _JWT.sub(REDACTED, line)
        line = _KNOWN_PREFIX.sub(REDACTED, line)
        if not _looks_like_json(line) and _REDACT_LINE.search(line):
            line = REDACTED
        out_lines.append(line)
    return "\n".join(out_lines)


def validate_name(value: str, *, field: str = "name") -> str:
    if not value or not _NAME_RE.match(value):
        raise ValueError(f"invalid {field}: {value!r}")
    return value


def validate_context(value: str) -> str:
    if not value or not _CONTEXT_RE.match(value):
        raise ValueError(f"invalid context: {value!r}")
    return value


def validate_kind(value: str) -> str:
    if not value or not _KIND_RE.match(value):
        raise ValueError(f"invalid kind: {value!r}")
    return value


def validate_incident_id(value: str) -> str:
    """Incident / evidence identifiers: permissive but path-safe."""
    if not value or not _INCIDENT_RE.match(value) or ".." in value:
        raise ValueError(f"invalid incident id: {value!r}")
    return value


def validate_tail(value: int, *, low: int = 1, high: int = 100_000) -> int:
    if not isinstance(value, int) or not (low <= value <= high):
        raise ValueError(f"tail out of range [{low}, {high}]: {value!r}")
    return value


# Kubernetes mutation verbs must never appear in any adapter argv.
_MUTATION_VERBS = {
    "apply", "create", "delete", "patch", "edit", "scale", "replace",
    "annotate", "label", "rollout", "set", "drain", "cordon", "taint",
    "expose", "run", "exec", "cp", "port-forward", "reconcile", "suspend",
    "resume", "upgrade", "uninstall", "install",
}


def assert_read_only(argv: list[str]) -> None:
    """Raise if an argv contains a Kubernetes/Flux/Helm mutation verb."""
    for token in argv:
        if token in _MUTATION_VERBS:
            raise PermissionError(f"read-only guard blocked token: {token!r}")


def origin_allowed(origin: str | None, allowed: list[str]) -> bool:
    if origin is None:
        return True  # non-browser client (curl, tests)
    return origin in allowed
