from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID


MODEL_MANIFEST_PATH = Path(__file__).resolve().parent / "manifests" / "model_versions.json"


@dataclass(frozen=True)
class ModelVersionManifest:
    model_version_uuid: UUID
    model_code: str
    version_no: int
    status: str
    parameters: dict[str, Any]
    implementation_sha256: str
    code_commit_sha: str | None


def load_model_version(model_version_uuid: UUID) -> ModelVersionManifest:
    payload = json.loads(MODEL_MANIFEST_PATH.read_text(encoding="utf-8"))
    raw = payload.get(str(model_version_uuid))
    if raw is None:
        raise RuntimeError(
            f"Modelo {model_version_uuid} ausente de {MODEL_MANIFEST_PATH.name}"
        )
    return ModelVersionManifest(
        model_version_uuid=model_version_uuid,
        model_code=raw["model_code"],
        version_no=int(raw["version_no"]),
        status=raw["status"],
        parameters=raw["parameters"],
        implementation_sha256=raw["implementation_sha256"],
        code_commit_sha=raw.get("code_commit_sha"),
    )
