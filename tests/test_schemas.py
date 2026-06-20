"""
tests/test_schemas.py
------------------------
Sprint 0 exit criteria: all 3 LOB schemas exist and validate against the
Pydantic LOBSchema model.
"""

import pytest

from core.schema_loader import SchemaNotFoundError, load_all_schemas, load_lob_schema
from core.schemas import LOB


@pytest.mark.parametrize("lob", [LOB.AUTO, LOB.PROPERTY, LOB.HEALTH])
def test_schema_loads_and_validates(lob):
    schema = load_lob_schema(lob)
    assert schema.lob == lob
    assert len(schema.sections) > 0
    assert len(schema.all_fields) > 0
    assert len(schema.mandatory_doc_types) > 0


def test_all_schemas_have_required_fields():
    for lob, schema in load_all_schemas().items():
        assert len(schema.required_fields) > 0, f"{lob} schema has no required fields"


def test_field_ids_unique_within_schema():
    for lob, schema in load_all_schemas().items():
        ids = [f.field_id for f in schema.all_fields]
        assert len(ids) == len(set(ids)), f"{lob} schema has duplicate field_ids"


def test_section_ids_unique_within_schema():
    for lob, schema in load_all_schemas().items():
        ids = [s.section_id for s in schema.sections]
        assert len(ids) == len(set(ids)), f"{lob} schema has duplicate section_ids"


def test_health_schema_explicitly_disclaims_acord():
    """Guards against accidentally re-labeling Health as ACORD-based later."""
    schema = load_lob_schema(LOB.HEALTH)
    assert "ACORD" in schema.source_concept
    assert "NOT ACORD" in schema.source_concept


def test_unknown_lob_raises():
    with pytest.raises(SchemaNotFoundError):
        load_lob_schema(LOB.UNKNOWN)


def test_get_section_lookup():
    schema = load_lob_schema(LOB.AUTO)
    section = schema.get_section("loss_details")
    assert section is not None
    assert any(f.field_id == "date_of_loss" for f in section.fields)
    assert schema.get_section("does_not_exist") is None
