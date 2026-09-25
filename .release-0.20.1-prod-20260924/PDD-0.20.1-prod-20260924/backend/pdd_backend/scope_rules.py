from __future__ import annotations

import json
from pathlib import Path
from typing import Any


POLICY_PATH = Path(__file__).resolve().parent / "rules" / "scope_exclusions.json"


def load_scope_exclusion_policy() -> dict[str, Any]:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if not str(policy.get("policy_code", "")).strip():
        raise ValueError("La politica de exclusiones debe tener policy_code")
    if not isinstance(policy.get("version"), int) or policy["version"] <= 0:
        raise ValueError("La version de exclusiones del scope debe ser positiva")
    rules = policy.get("rules")
    if not isinstance(rules, list):
        raise ValueError("La politica de exclusiones debe contener una lista rules")

    seen: set[tuple[int, int]] = set()
    seen_rule_codes: set[str] = set()
    for rule in rules:
        required = {
            "rule_code",
            "c_rubro",
            "c_subrubro_1",
            "reason",
        }
        missing = required.difference(rule)
        if missing:
            raise ValueError(
                "Regla de exclusion incompleta; faltan: " + ", ".join(sorted(missing))
            )
        key = (int(rule["c_rubro"]), int(rule["c_subrubro_1"]))
        if key in seen:
            raise ValueError(f"Categoria excluida duplicada: {key}")
        seen.add(key)
        rule_code = str(rule["rule_code"]).strip()
        if not rule_code or rule_code in seen_rule_codes:
            raise ValueError(f"rule_code vacio o duplicado: {rule_code!r}")
        seen_rule_codes.add(rule_code)

    return policy


def scope_exclusion_policy_json() -> str:
    return json.dumps(
        load_scope_exclusion_policy(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
