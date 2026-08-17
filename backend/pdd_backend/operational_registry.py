from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID


CONFIGURATION_MANIFEST_PATH = (
    Path(__file__).resolve().parent
    / "manifests"
    / "operational_configurations.json"
)


@dataclass(frozen=True)
class OperationalConfiguration:
    configuration_version_uuid: UUID
    configuration_code: str
    version_no: int
    status: str
    valid_from: date
    parameters: dict[str, Any]
    checksum: str


def configuration_checksum(parameters: dict[str, Any]) -> str:
    payload = json.dumps(
        parameters,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_operational_configuration(
    configuration_version_uuid: UUID,
) -> OperationalConfiguration:
    payload = json.loads(CONFIGURATION_MANIFEST_PATH.read_text(encoding="utf-8"))
    raw = payload.get(str(configuration_version_uuid))
    if raw is None:
        raise RuntimeError(
            f"Configuracion {configuration_version_uuid} ausente de "
            f"{CONFIGURATION_MANIFEST_PATH.name}"
        )
    parameters = raw["parameters"]
    return OperationalConfiguration(
        configuration_version_uuid=configuration_version_uuid,
        configuration_code=raw["configuration_code"],
        version_no=int(raw["version_no"]),
        status=raw["status"],
        valid_from=date.fromisoformat(raw["valid_from"]),
        parameters=parameters,
        checksum=configuration_checksum(parameters),
    )
