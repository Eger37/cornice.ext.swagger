import unittest

import colander
from cornice_swagger.converters import TypeConversionDispatcher
from cornice_swagger.converters import convert_schema as convert
from cornice_swagger.converters.exceptions import NoSuchConverter

from ..support import AnyType, AnyTypeConverter


class ConversionTest(unittest.TestCase):
    def test_validate_all(self):
        node = colander.SchemaNode(
            colander.String(),
            validator=colander.All(colander.Length(12, 42), colander.Regex(r"foo*bar")),
        )
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "string",
                "pattern": "foo*bar",
                "maxLength": 42,
                "minLength": 12,
            },
        )

    def test_support_custom_converters(self):
        node = colander.SchemaNode(AnyType())
        custom_converters = {AnyType: AnyTypeConverter}
        converter = TypeConversionDispatcher(custom_converters)
        ret = converter(node)
        self.assertEquals(ret, {})

    def test_support_default_converter(self):
        node = colander.SchemaNode(AnyType())
        converter = TypeConversionDispatcher(default_converter=AnyTypeConverter)
        ret = converter(node)
        self.assertEquals(ret, {})

    def test_raise_no_such_converter_on_invalid_type(self):
        node = colander.SchemaNode(dict)
        self.assertRaises(NoSuchConverter, convert, node)


class StringConversionTest(unittest.TestCase):
    def test_sanity(self):
        node = colander.SchemaNode(colander.String())
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "string",
            },
        )

    def test_validate_default(self):
        node = colander.SchemaNode(colander.String(), missing="foo")
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "string",
                "default": "foo",
            },
        )

    def test_validate_length(self):
        node = colander.SchemaNode(colander.String(), validator=colander.Length(12, 42))
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "string",
                "maxLength": 42,
                "minLength": 12,
            },
        )

    def test_validate_regex(self):
        node = colander.SchemaNode(colander.String(), validator=colander.Regex(r"foo*bar"))
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "string",
                "pattern": "foo*bar",
            },
        )

    def test_validate_regex_email(self):
        node = colander.SchemaNode(colander.String(), validator=colander.Email())
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "string",
                "format": "email",
            },
        )

    def test_validate_regex_url(self):
        node = colander.SchemaNode(colander.String(), validator=colander.url)
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "string",
                "format": "url",
            },
        )

    def test_validate_oneof(self):
        node = colander.SchemaNode(colander.String(), validator=colander.OneOf(["one", "two"]))
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "string",
                "enum": ["one", "two"],
            },
        )

    def test_title(self):
        node = colander.SchemaNode(colander.String(), title="foo")
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "string",
                "title": "foo",
            },
        )

    def test_description(self):
        node = colander.SchemaNode(colander.String(), description="bar")
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "string",
                "description": "bar",
            },
        )


class IntegerConversionTest(unittest.TestCase):
    def test_sanity(self):
        node = colander.SchemaNode(colander.Integer())
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "integer",
            },
        )

    def test_default(self):
        node = colander.SchemaNode(colander.Integer(), missing=1)
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "integer",
                "default": 1,
            },
        )

    def test_enum(self):
        node = colander.SchemaNode(colander.Integer(), validator=colander.OneOf([1, 2, 3, 4]))
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "integer",
                "enum": [1, 2, 3, 4],
            },
        )

    def test_range(self):
        node = colander.SchemaNode(colander.Integer(), validator=colander.Range(111, 555))
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "integer",
                "minimum": 111,
                "maximum": 555,
            },
        )


class DateTimeConversionTest(unittest.TestCase):
    def test_sanity(self):
        node = colander.SchemaNode(colander.DateTime())
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "string",
                "format": "date-time",
            },
        )


class MappingConversionTest(unittest.TestCase):
    def test_sanity(self):
        node = colander.MappingSchema()
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "object",
            },
        )

    def test_required(self):
        class Mapping(colander.MappingSchema):
            foo = colander.SchemaNode(colander.String())

        node = Mapping()
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "object",
                "properties": {"foo": {"title": "Foo", "type": "string"}},
                "required": ["foo"],
            },
        )

    def test_not_required(self):
        class Mapping(colander.MappingSchema):
            foo = colander.SchemaNode(colander.String(), missing=colander.drop)

        node = Mapping()
        ret = convert(node)
        self.assertDictEqual(
            ret,
            {
                "type": "object",
                "properties": {"foo": {"title": "Foo", "type": "string"}},
            },
        )

    def test_nested_schema(self):
        class BaseMapping(colander.MappingSchema):
            foo = colander.SchemaNode(colander.String(), missing=colander.drop)

        class TopMapping(colander.MappingSchema):
            bar = BaseMapping(missing=colander.drop)

        node = TopMapping()
        ret = convert(node)
        self.assertDictEqual(ret, {
            'type': 'object',
            'properties': {
                'bar': {
                    'title': 'Bar',
                    'type': 'object',
                    'properties': {
                        'foo': {
                            'title': 'Foo',
                            'type': 'string'
                        }
                    }
                }
            },
        })

    def test_oneOf_nested_schema(self):
        class Mapping(colander.MappingSchema):
            foo = colander.SchemaNode(colander.String(),
                                      missing=colander.drop)

            @staticmethod
            def schema_type():
                return colander.Mapping(unknown='preserve')

        node = Mapping()
        ret = convert(node)
        self.assertDictEqual(ret, {
            'type': 'object',
            'properties': {
                'foo': {
                    'title': 'Foo',
                    'type': 'string'
                }
            },
            'additionalProperties': {}
        })

    def test_oneOf_primitive_schema(self):
        class Mapping(colander.MappingSchema):
            foo = colander.SchemaNode(colander.String())
            bar = colander.SchemaNode(colander.Integer())

        schema = Mapping(validator=colander.OneOf(['foo', 'bar']))
        ret = convert(schema)
        self.assertDictEqual(ret, {
            'oneOf': [
                {
                    'type': 'string',
                    'title': 'Foo'
                },
                {
                    'type': 'integer',
                    'title': 'Bar'
                }
            ]
        })

    def test_oneOf_object_schema(self):
        class MappingStr(colander.MappingSchema):
            foo = colander.SchemaNode(colander.String())

        class MappingInt(colander.MappingSchema):
            bar = colander.SchemaNode(colander.Integer(),
                                      missing=colander.drop)

        class MappingTop(colander.MappingSchema):
            str = MappingStr()
            int = MappingInt()

        class MappingTop2(colander.MappingSchema):
            str = MappingStr(missing=colander.drop)
            int = MappingInt(missing=colander.drop)
            validator = colander.OneOf(['str', 'int'])

        schema2 = MappingTop2(validator=colander.Function(
            lambda value: isinstance(value, dict) and
            any([k in value for k in ['int', 'str']])
        ))
        schema2.deserialize({'int': {'bar': 1}})

        schema = MappingTop(validator=colander.OneOf(['str', 'int']))
        ret = convert(schema)
        self.assertDictEqual(ret, {
            'oneOf': [
                {
                    'type': 'object',
                    'title': 'Str',
                    'properties': {
                        'foo': {
                            'type': 'string',
                            'title': 'Foo'
                        }
                    },
                    'required': ['foo']
                },
                {
                    'type': 'object',
                    'title': 'Int',
                    'properties': {
                        'bar': {
                            'type': 'integer',
                            'title': 'Bar'
                        }
                    }
                }
            ]
        })

    def test_oneOf_nested_schema(self):
        class Mapping(colander.MappingSchema):
            foo = colander.SchemaNode(colander.String())
            bar = colander.SchemaNode(colander.Integer())

        class MappingTop(colander.MappingSchema):
            obj = Mapping(validator=colander.OneOf(['foo', 'bar']))

        schema = MappingTop()
        ret = convert(schema)
        self.assertDictEqual(ret, {
            'type': 'object',
            'properties': {
                'obj': {
                    'oneOf': [
                        {
                            'type': 'string',
                            'title': 'Foo'
                        },
                        {
                            'type': 'integer',
                            'title': 'Bar'
                        }
                    ]
                }
            },
            'required': ['obj']
        })


class SequenceConversionTest(unittest.TestCase):

    def test_primitive_sequence(self):

        class Integers(colander.SequenceSchema):
            num = colander.SchemaNode(colander.Integer())

        schema = Integers()
        ret = convert(schema)
        self.assertDictEqual(ret, {
            'type': 'array',
            'items': {
                'title': 'Num',
                'type': 'integer',
            },
            'title': 'Integers'
        })

    def test_mapping_sequence(self):

        class BaseMapping(colander.MappingSchema):
            name = colander.SchemaNode(colander.String())
            number = colander.SchemaNode(colander.Integer())

        class BaseMappings(colander.SequenceSchema):
            base_mapping = BaseMapping()

        schema = BaseMappings()
        ret = convert(schema)

        self.assertDictEqual(ret, {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'name': {
                        'type': 'string',
                        'title': 'Name',
                    },
                    'number': {
                        'type': 'integer',
                        'title': 'Number',
                    }
                },
                'required': ['name', 'number'],
                'title': 'Base Mapping'
            },
            'title': 'BaseMappings'
        })

    def test_oneOf_primitive_sequence(self):
        class MappingItem(colander.MappingSchema):
            foo = colander.SchemaNode(colander.String())
            bar = colander.SchemaNode(colander.Integer())

        class Sequence(colander.SequenceSchema):
            item = MappingItem(validator=colander.OneOf(['foo', 'bar']))

        schema = Sequence()
        ret = convert(schema)
        self.maxDiff = None
        self.assertDictEqual(ret, {
            'type': 'array',
            'items': {
                'oneOf': [
                    {
                        'type': 'string',
                        'title': 'Foo'
                    },
                    {
                        'type': 'integer',
                        'title': 'Bar'
                    }
                ]
            },
            'title': 'Sequence'
        })

    def test_oneOf_mapping_sequence(self):
        class MappingStr(colander.MappingSchema):
            foo = colander.SchemaNode(colander.String())

        class MappingInt(colander.MappingSchema):
            bar = colander.SchemaNode(colander.Integer())

        class MappingItem(colander.MappingSchema):
            int = MappingInt()
            str = MappingStr()

        class Sequence(colander.SequenceSchema):
            item = MappingItem(validator=colander.OneOf(['foo', 'bar']))

        schema = Sequence()
        ret = convert(schema)
        self.assertIn('type', ret)
        self.assertEqual(ret['type'], 'array')
        self.assertIn('items', ret)
        self.assertIn('oneOf', ret['items'])
        self.assertIsInstance(ret['items']['oneOf'], list)

        expected_oneof = [
            {
                'type': 'object',
                'title': 'Str',
                'properties': {
                    'foo': {
                        'type': 'string',
                        'title': 'Foo',
                    }
                },
                'required': ['foo']
            },
            {
                'type': 'object',
                'title': 'Int',
                'properties': {
                    'bar': {
                        'type': 'integer',
                        'title': 'Bar',
                    }
                },
                'required': ['bar']
            }
        ]
        self.assertListEqual(sorted(ret['items']['oneOf'], key=lambda x: x['title']),
                             sorted(expected_oneof, key=lambda x: x['title']))
