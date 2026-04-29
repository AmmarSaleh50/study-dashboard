"""Tests for app/services/_helpers.py."""
from pydantic import BaseModel

from app.services._helpers import validated_cols


class _SampleSchema(BaseModel):
    name: str
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
