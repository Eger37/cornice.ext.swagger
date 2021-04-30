"""
These are many common schema definitions that are very recurrent in Web Applications.
They can be employed as is, or extended, at your own convenience.
"""
import re
import colander

from cornice_swagger.openapi import ExtendedSchemaNode, ExtendedString as String, SchemaNodeTypeError


class SchemeURL(colander.Regex):
    """
    String representation of an URL with extended set of allowed URI schemes.

    .. seealso::
        :class:`colander.url` [remote http(s)/ftp(s)]
        :class:`colander.file_uri` [local file://]
    """
    def __init__(self, schemes=None, msg=None, flags=re.IGNORECASE):
        if not schemes:
            schemes = [""]
        if not msg:
            msg = colander._("Must be a URL matching one of schemes {}".format(schemes))  # noqa
        regex_schemes = r"(?:" + "|".join(schemes) + r")"
        regex = colander.URL_REGEX.replace(r"(?:http|ftp)s?", regex_schemes)
        super(SchemeURL, self).__init__(regex, msg=msg, flags=flags)


class SLUG(ExtendedSchemaNode):
    schema_type = String
    description = "Slug name pattern."
    example = "some-object-slug-name"
    pattern = "^[A-Za-z0-9]+(?:(-|_)[A-Za-z0-9]+)*$"


class UUID(ExtendedSchemaNode):
    schema_type = String
    description = "Unique identifier."
    example = "a9d14bf4-84e0-449a-bac8-16e598efe807"
    format = "uuid"
    title = "UUID"


class URL(ExtendedSchemaNode):
    schema_type = String
    description = "URL reference."
    format = "url"


class FileLocal(ExtendedSchemaNode):
    schema_type = String
    description = "Local file reference."
    format = "file"
    validator = colander.Regex(r"^(file://)?(?:/|[/?]\S+)$")


class FileURL(ExtendedSchemaNode):
    schema_type = String
    description = "URL file reference."
    format = "url"
    validator = SchemeURL(schemes=["http", "https"])


class OneOfCaseInsensitive(colander.OneOf):
    """
    Validator that ensures the given value matches one of the available choices, but allowing case insensitive values.
    """
    def __call__(self, node, value):
        if str(value).lower() not in (choice.lower() for choice in self.choices):
            return super(OneOfCaseInsensitive, self).__call__(node, value)


class StringRange(colander.Range):
    """
    Validator that provides the same functionalities as :class:`colander.Range` for a numerical string value.
    """
    def __init__(self, min=None, max=None, **kwargs):
        try:
            if isinstance(min, str):
                min = int(min)
            if isinstance(max, str):
                max = int(max)
        except ValueError:
            raise SchemaNodeTypeError("StringRange validator created with invalid min/max non-numeric string.")
        super(StringRange, self).__init__(min=min, max=max, **kwargs)

    def __call__(self, node, value):
        if not isinstance(value, str):
            raise colander.Invalid(node=node, value=value, msg="Value is not a string.")
        if not str.isnumeric(value):
            raise colander.Invalid(node=node, value=value, msg="Value is not a numeric string.")
        return super(StringRange, self).__call__(node, int(value))


class SemanticVersion(colander.Regex):
    """
    String representation that is valid against Semantic Versioning specification.

    .. seealso::
        https://semver.org/
    """

    def __init__(self, *args, v_prefix=False, rc_suffix=True, **kwargs):
        if "regex" in kwargs:
            self.pattern = kwargs.pop("regex")
        else:
            v_prefix = "v" if v_prefix else ""
            rc_suffix = r"(\.[a-zA-Z0-9\-_]+)*" if rc_suffix else ""
            self.pattern = (
                r"^"
                + v_prefix +
                r"\d+"      # major
                r"(\.\d+"   # minor
                r"(\.\d+"   # patch
                + rc_suffix +
                r")*)*$"
            )
        super(SemanticVersion, self).__init__(regex=self.pattern, *args, **kwargs)
