"""Shared helpers for services."""
from typing import Any, Dict, Iterable
from pydantic import BaseModel


def model_dump_clean(m: BaseModel) -> Dict[str, Any]:
    """Serialize a Pydantic model to JSON-compatible dict (exclude unset + None)."""
    return m.model_dump(mode="json", exclude_none=True, exclude_unset=True)


def only(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any] | None:
    for r in rows:
        return r
    return None


def validated_cols(schema_cls: type[BaseModel], data: Dict[str, Any]) -> list[str]:
    """Filter `data` keys to those declared as fields on `schema_cls`.

    Defense in depth for the f-string-column-name pattern in services'
    `INSERT (...)` / `UPDATE SET ...` SQL: even though Pydantic models
    default to `extra="ignore"` (so `model_dump()` only emits declared
    fields), wrapping every column-list construction through this helper
    keeps the property explicit at the SQL boundary. A future schema
    bug — `extra="allow"` flipped on, a pre-validator that injects a
    column name, an alias mishandled — would silently widen the SQL
    surface without it.

    Returns a list preserving `data`'s key insertion order so the
    f-stringed `INSERT (col1, col2, ...) VALUES (%s, %s, ...)` stays
    deterministic and matches the parameter tuple order.
    """
    allowed = set(schema_cls.model_fields.keys())
    return [k for k in data.keys() if k in allowed]
