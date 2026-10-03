"""Evidence browser backed by the engine's local evidence bundles."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..config import settings


def _evidence_root() -> Path:
    # The engine writes evidence beneath $HOME/.devopssentinel/evidence/<ID>.
    root = Path(os.environ.get("HOME", str(Path.home()))) / ".devopssentinel" / "evidence"
    return root


def list_incidents() -> list[dict[str, Any]]:
    root = _evidence_root()
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        files = [f for f in child.rglob("*") if f.is_file()]
        out.append(
            {
                "id": child.name,
                "files": len(files),
                "bytes": sum(f.stat().st_size for f in files),
                "modified": int(child.stat().st_mtime),
            }
        )
    return out


def list_evidence(incident_id: str) -> list[dict[str, Any]]:
    safe = incident_id.replace("/", "").replace("\\", "").replace("..", "")
    base = _evidence_root() / safe
    if not base.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for f in sorted(base.rglob("*")):
        if f.is_file():
            out.append(
                {
                    "path": str(f.relative_to(base)).replace("\\", "/"),
                    "bytes": f.stat().st_size,
                    "modified": int(f.stat().st_mtime),
                }
            )
    return out


def read_evidence(incident_id: str, rel_path: str, limit: int = 200_000) -> str:
    safe = incident_id.replace("/", "").replace("\\", "").replace("..", "")
    base = _evidence_root() / safe
    target = (base / rel_path).resolve()
    if base.resolve() not in target.parents and target != base.resolve():
        raise PermissionError("path escapes evidence root")
    if not target.is_file():
        raise FileNotFoundError(rel_path)
    text = target.read_text(encoding="utf-8", errors="replace")
    return text[:limit]


def export_payload(name: str, payload: Any, fmt: str) -> tuple[str, str, str]:
    """Return (filename, media_type, body) for a local download."""
    from ..security import redact_text

    if fmt == "json":
        import json

        body = redact_text(json.dumps(payload, indent=2))
        return f"{name}.json", "application/json", body
    if fmt == "ndjson":
        import json

        rows = payload if isinstance(payload, list) else [payload]
        body = "\n".join(redact_text(json.dumps(r)) for r in rows)
        return f"{name}.ndjson", "application/x-ndjson", body
    if fmt == "csv":
        import csv
        import io

        rows = payload if isinstance(payload, list) else [payload]
        buffer = io.StringIO()
        if rows and isinstance(rows[0], dict):
            writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return f"{name}.csv", "text/csv", redact_text(buffer.getvalue())
    # txt fallback
    if isinstance(payload, str):
        body = payload
    else:
        import json

        body = json.dumps(payload, indent=2)
    return f"{name}.txt", "text/plain", redact_text(body)


STATE_DIR = settings.state_dir
