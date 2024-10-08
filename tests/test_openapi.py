#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests for :mod:`cornice_swagger.openapi` utilities.
"""
import colander
import pytest

from cornice_swagger import openapi as oas
from examples.openapi import InputsDefinition


def test_oneof_io_formats_deserialize_as_mapping():
    """
    Evaluates OneOf deserialization using the example inputs definition
    """
    data = {
        "input-1": {"type": "float"},
        "input-2": {"type": "File"},
        "input-3": {"type": {"type": "array", "items": "string"}}
    }

    result = InputsDefinition(name=__name__).deserialize(data)
    assert isinstance(result, dict)
    assert all(input_key in result for input_key in ["input-1", "input-2", "input-3"])
    assert result["input-1"]["type"] == "float"
    assert result["input-2"]["type"] == "File"
    assert isinstance(result["input-3"]["type"], dict)
    assert result["input-3"]["type"]["type"] == "array"
    assert result["input-3"]["type"]["items"] == "string"


def test_oneof_io_formats_deserialize_as_listing():
    """
    Evaluates OneOf deserialization for inputs/outputs CWL definition specified as list of objects.
    Should work simultaneously with the mapping variation using the same deserializer.

    .. seealso::
        - :func:`test_cwl_deploy_io_deserialize_mapping`
    """
    data = [
        {"id": "input-1", "type": "float"},
        {"id": "input-2", "type": "File"},
        {"id": "input-3", "type": {"type": "array", "items": "string"}}
    ]

    result = sd.InputsDefinition(name=__name__).deserialize(data)
    assert isinstance(result, list)
    assert all(result[i]["id"] == input_key for i, input_key in enumerate(["input-1", "input-2", "input-3"]))
    assert result[0]["type"] == "float"
    assert result[1]["type"] == "File"
    assert isinstance(result[2]["type"], dict)
    assert result[2]["type"]["type"] == "array"
    assert result[2]["type"]["items"] == "string"


def test_any_of_under_variable():
    class ValueObject(oas.ExtendedMappingSchema):
        value = oas.ExtendedFloat()

    class ValueType(oas.OneOfKeywordSchema):
        _one_of = [
            oas.ExtendedString(),
            oas.ExtendedInteger(),
            ValueObject(),
        ]

    class VariableMap(oas.PermissiveMappingSchema):
        var_key = ValueType(variable="<var-key>", title="Some", description="Some value under any key.")

    # all the first level keys don't matter here
    test = {
        "dont-care": 1,
        "really-anything": "ok",
        "even-nested-but-the-value-key-below-matters": {
            "value": 3.4
        }
    }
    result = VariableMap().deserialize(test)
    assert isinstance(result, dict)
    assert all(k in result for k in test)
    assert test == result


def test_oneof_nested_dict_list():
    class Seq(oas.ExtendedSequenceSchema):
        item = oas.ExtendedSchemaNode(colander.String())

    class Obj(oas.ExtendedMappingSchema):
        key = oas.ExtendedSchemaNode(colander.String())

    class ObjSeq(oas.ExtendedMappingSchema):
        items = Seq()

    class ObjOneOf(oas.OneOfKeywordSchema):
        _one_of = (Obj, ObjSeq)

    for test_schema, test_value in [
        (ObjOneOf, {"key": "value"}),
        (ObjOneOf, {"items": ["value"]})
    ]:
        try:
            assert test_schema().deserialize(test_value) == test_value
        except colander.Invalid:
            pytest.fail("Should not fail deserialize of '{!s}' with {!s}"
                        .format(oas._get_node_name(test_schema), test_value))
    for test_schema, test_value in [
        (ObjOneOf, {"key": None}),
        (ObjOneOf, {"items": None}),
        (ObjOneOf, {"items": ["value"], "key": "value"}),  # cannot have both (oneOf)
    ]:
        try:
            result = ObjOneOf().deserialize(test_value)
        except colander.Invalid:
            pass
        except Exception:
            raise AssertionError("Incorrect exception raised from deserialize of '{!s}' with {!s}"
                                 .format(oas._get_node_name(test_schema), test_value))
        else:
            raise AssertionError("Should have raised invalid schema from deserialize of '{!s}' with {!s}, but got {!s}"
                                 .format(oas._get_node_name(test_schema), test_value, result))


class FieldTestString(oas.ExtendedSchemaNode):
    schema_type = colander.String


class Mapping(oas.ExtendedMappingSchema):
    test = FieldTestString()
    schema_expected = {
        "type": "object",
        "title": "Mapping",
        "required": ["test"],
        "properties": {
            "test": {
                "title": "test",
                "type": "string",
            }
        }
    }


class Default(oas.ExtendedMappingSchema):
    test = FieldTestString(default="test")
    schema_expected = {
        "type": "object",
        "title": "Default",
        "properties": {
            "test": {
                "default": "test",
                "title": "test",
                "type": "string",
            }
        }
    }


class Missing(oas.ExtendedMappingSchema):
    test = FieldTestString(missing=colander.drop)
    schema_expected = {
        "type": "object",
        "title": "Missing",
        "properties": {
            "test": {
                "title": "test",
                "type": "string",
            }
        }
    }


class DefaultMissing(oas.ExtendedMappingSchema):
    test = FieldTestString(default="test", missing=colander.drop)
    schema_expected = {
        "type": "object",
        "title": "DefaultMissing",
        "properties": {
            "test": {
                "default": "test",
                "title": "test",
                "type": "string",
            }
        }
    }


class DefaultMissingValidator(oas.ExtendedMappingSchema):
    test = FieldTestString(default="test", missing=colander.drop, validator=colander.OneOf(["test"]))
    schema_expected = {
        "type": "object",
        "title": "DefaultMissingValidator",
        "properties": {
            "test": {
                "default": "test",
                "title": "test",
                "type": "string",
                "enum": ["test"],
            }
        }
    }


class Validator(oas.ExtendedMappingSchema):
    test = FieldTestString(validator=colander.OneOf(["test"]))
    schema_expected = {
        "type": "object",
        "title": "Validator",
        "required": ["test"],
        "properties": {
            "test": {
                "title": "test",
                "type": "string",
                "enum": ["test"],
            }
        }
    }


class DefaultDropValidator(oas.ExtendedMappingSchema):
    """Definition that will allow only the specific validator values, or drops the content silently."""
    test = FieldTestString(default=colander.drop, validator=colander.OneOf(["test"]))
    schema_expected = {
        "type": "object",
        "title": "DefaultDropValidator",
        "properties": {
            "test": {
                "title": "test",
                "type": "string",
                "enum": ["test"],
            }
        }
    }


class DefaultDropRequired(oas.ExtendedMappingSchema):
    """
    Definition that will allow only the specific validator values, or drops the full content silently.
    One top of that, ensures that the resulting OpenAPI schema defines it as required instead of optional
    when default is usually specified.

    This allows dropping invalid values that failed validation and not employ any default, while letting know
    in the OpenAPI specification that for a nested definition of required elements, they will be used only if
    correctly provided, or completely ignored as optional.
    """
    test = FieldTestString(default=colander.drop, missing=colander.required, validator=colander.OneOf(["test"]))
    schema_expected = {
        "type": "object",
        "title": "DefaultDropRequired",
        "required": ["test"],
        "properties": {
            "test": {
                "title": "test",
                "type": "string",
                "enum": ["test"],
            }
        }
    }


class DefaultValidator(oas.ExtendedMappingSchema):
    """
    Functionality that we want most of the time to make an 'optional' but validated value.

    When value is explicitly provided, raise if invalid according to condition.
    Otherwise, use default if omitted.
    """
    test = FieldTestString(default="test", validator=colander.OneOf(["test"]))
    schema_expected = {
        "type": "object",
        "title": "DefaultValidator",
        "properties": {
            "test": {
                "default": "test",
                "title": "test",
                "type": "string",
                "enum": ["test"],
            }
        }
    }


class MissingValidator(oas.ExtendedMappingSchema):
    test = FieldTestString(missing=colander.drop, validator=colander.OneOf(["test"]))
    schema_expected = {
        "type": "object",
        "title": "MissingValidator",
        "properties": {
            "test": {
                "title": "test",
                "type": "string",
                "enum": ["test"],
            }
        }
    }


def test_invalid_schema_mismatch_default_validator():
    try:
        class TestBad(oas.ExtendedSchemaNode):
            schema_type = colander.String
            default = "bad-value-not-in-one-of"
            validator = colander.OneOf(["test"])

        TestBad()
    except oas.SchemaNodeTypeError:
        pass
    else:
        pytest.fail("Erroneous schema must raise immediately if default doesn't conform to its own validator.")
    try:
        class DefaultValidatorBad(oas.ExtendedMappingSchema):
            test = FieldTestString(default="bad-value-not-in-one-of", validator=colander.OneOf(["test"]))

        DefaultValidatorBad()
    except oas.SchemaNodeTypeError:
        pass
    else:
        pytest.fail("Erroneous schema must raise immediately if default doesn't conform to its own validator.")


def test_schema_default_missing_validator_combinations():
    """
    Validate resulting deserialization of mappings according to parameter combinations and parsed data.

    .. seealso::
        :func:`test_schema_default_missing_validator_openapi`
    """
    test_schemas = [
        (Mapping, {}, colander.Invalid),                    # required but missing
        (Mapping, {"test": None}, colander.Invalid),        # wrong value schema-type
        (Mapping, {"test": "random"}, {"test": "random"}),  # uses the value as is if provided because no validator
        (Default, {}, {"test": "test"}),                    # default+required adds the value if omitted
        (Default, {"test": None}, {"test": "test"}),        # default+required sets the value if null
        (Default, {"test": "random"}, {"test": "random"}),  # default+required uses the value as is if provided
        (Missing, {}, {}),                                  # missing only drops the value if omitted
        (Missing, {"test": None}, {}),
        (Missing, {"test": "random"}, {"test": "random"}),
        (DefaultMissing, {}, {"test": "test"}),             # default+missing ignores drops and sets omitted value
        (DefaultMissing, {"test": None}, {}),
        (DefaultMissing, {"test": "random"}, {"test": "random"}),
        (Validator, {}, colander.Invalid),
        (Validator, {"test": None}, colander.Invalid),
        (Validator, {"test": "bad"}, colander.Invalid),
        (Validator, {"test": "test"}, {"test": "test"}),
        (DefaultValidator, {}, {"test": "test"}),
        (DefaultValidator, {"test": None}, {"test": "test"}),
        (DefaultValidator, {"test": "bad"}, colander.Invalid),
        (DefaultValidator, {"test": "test"}, {"test": "test"}),
        (DefaultMissingValidator, {}, {"test": "test"}),    # default+missing ignores drop and sets default if omitted
        (DefaultMissingValidator, {"test": None}, {}),
        # (DefaultMissingValidator, {"test": "bad"}, {}),
        (DefaultMissingValidator, {"test": "bad"}, colander.Invalid),
        (DefaultMissingValidator, {"test": "test"}, {"test": "test"}),
        (MissingValidator, {}, {}),
        (MissingValidator, {"test": None}, {}),
        # (MissingValidator, {"test": "bad"}, {}),
        (MissingValidator, {"test": "bad"}, colander.Invalid),
        (MissingValidator, {"test": "test"}, {"test": "test"}),
        (DefaultDropRequired, {}, {}),
        (DefaultDropRequired, {"test": None}, {}),
        (DefaultDropRequired, {"test": "bad"}, {}),
        (DefaultDropRequired, {"test": "test"}, {"test": "test"}),
        (DefaultDropValidator, {}, {}),
        (DefaultDropValidator, {"test": None}, {}),
        (DefaultDropValidator, {"test": "bad"}, {}),
        (DefaultDropValidator, {"test": "test"}, {"test": "test"}),
    ]

    for test_schema, test_value, test_expect in test_schemas:
        try:
            result = test_schema().deserialize(test_value)
            if test_expect is colander.Invalid:
                pytest.fail("Expected invalid format from [{}] with [{}]".format(test_schema.__name__, test_value))
            assert result == test_expect, "Bad result from [{}] with [{}]".format(test_schema.__name__, test_value)
        except colander.Invalid:
            if test_expect is colander.Invalid:
                pass
            else:
                pytest.fail("Expected valid format from [{}] with [{}]".format(test_schema.__name__, test_value))


def test_schema_default_missing_validator_openapi():
    """
    Validate that resulting OpenAPI schema are as expected while still providing advanced deserialization features.

    Resulting schema are very similar can often cannot be distinguished for some variants, but the various combination
    of values for ``default``, ``missing`` and ``validator`` will provide very distinct behavior during parsing.

    .. seealso::
        :func:`test_schema_default_missing_validator_combinations`
    """
    converter = oas.ObjectTypeConverter(oas.OAS3TypeConversionDispatcher())
    test_schemas = [
        Mapping,
        Missing,
        Default,
        Validator,
        DefaultMissing,
        DefaultValidator,
        MissingValidator,
        DefaultMissingValidator,
        DefaultDropValidator,
        DefaultDropRequired,
    ]
    for schema in test_schemas:
        converted = converter.convert_type(schema())
        assert converted == schema.schema_expected, "Schema for [{}] not as expected".format(schema.__name__)
