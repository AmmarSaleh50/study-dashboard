"""Tests for app/services/_helpers.py."""
from pydantic import BaseModel, Field

from app.services._helpers import validated_cols


class _SampleSchema(BaseModel):
    name: str
    age: int


class _AliasedSchema(BaseModel):
    """Schema with an aliased field — validated_cols must use the field name,
    not the alias, so the column name in the SQL matches the DB column."""
    display_name: str = Field(alias="displayName")
    age: int


def test_validated_cols_known_field_passes():
    cols = validated_cols(_SampleSchema, {"name": "Ammar", "age": 25})
    assert cols == ["name", "age"]


def test_validated_cols_unknown_field_filtered():
    # "secret" is NOT declared on the schema — it gets dropped.
    cols = validated_cols(_SampleSchema, {"name": "Ammar", "secret": "hax"})
    assert cols == ["name"]


def test_validated_cols_empty_data():
    assert validated_cols(_SampleSchema, {}) == []


def test_validated_cols_preserves_insertion_order():
    # f-stringed INSERT (col1, col2) VALUES (%s, %s) requires the column
    # list and the parameter tuple to match — so order must be stable
    # against the input dict.
    cols = validated_cols(_SampleSchema, {"age": 30, "name": "Ammar"})
    assert cols == ["age", "name"]


def test_validated_cols_drops_all_when_all_unknown():
    cols = validated_cols(_SampleSchema, {"foo": 1, "bar": 2})
    assert cols == []


# ── P2 regression: alias= fields ─────────────────────────────────────────────


def test_validated_cols_alias_field_accepted_by_python_name():
    """validated_cols uses model_fields (Python names), NOT aliases.

    A schema with Field(alias='displayName') defines a field whose Python
    name is 'display_name' and whose alias is 'displayName'.  validated_cols
    must accept the Python name (which is what model_dump() emits) and
    reject the alias — preventing alias-injected column names from leaking
    into SQL.
    """
    # Python name → accepted.
    cols = validated_cols(_AliasedSchema, {"display_name": "Ammar", "age": 25})
    assert cols == ["display_name", "age"]


def test_validated_cols_alias_is_rejected():
    """The alias string must NOT slip through as a column name.

    If it did, the f-stringed INSERT/UPDATE would inject an unrecognised
    column name (SQL injection surface at the schema boundary).
    """
    # Alias key → rejected (not in model_fields.keys()).
    cols = validated_cols(_AliasedSchema, {"displayName": "Ammar", "age": 25})
    assert "displayName" not in cols
    assert cols == ["age"]
