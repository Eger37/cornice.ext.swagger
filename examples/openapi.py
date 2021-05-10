"""
This module should contain any and every definitions in use to build the swagger UI,
so that one can update the swagger without touching any other files after the initial integration
"""
# pylint: disable=C0103,invalid-name

import argparse
import datetime
import enum
import os
import sys
import yaml

from colander import DateTime, Email, Enum, Range, drop, required
from cornice import Service
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPBadRequest, HTTPCreated, HTTPConflict, HTTPNotFound, HTTPNotImplemented, HTTPOk
from wsgiref.simple_server import make_server

# OpenAPI definition employ 'Extended<>' variants that provide more features over original colander types
# They are completely compatible with the originals, but special keywords specific to OpenAPI will only work when
# they are employed.
#
# To help migrate existing Swagger 2.0 schema definitions that you could have in your own code, it is enough to
# import them with aliases as presented below. No need to change the rest of the code
# (unless of course you want to add OpenAPI specific features, like OneOf, AnyOf, etc. keywords)
from cornice_swagger.openapi import (
    # AllOf, AnyOf, OneOf and Not keywords work like Mapping (a JSON object)
    # but they must have their special keyword within their definition, with a list of items contained in them
    # Of course, they can be nested as must as needed.
    AllOfKeywordSchema,
    AnyOfKeywordSchema,
    OneOfKeywordSchema,
    NotKeywordSchema,
    # Extended schemas with extra features for OpenAPI v3 and other goodies
    ExtendedBoolean as Boolean,
    ExtendedFloat as Float,
    ExtendedInteger as Integer,
    ExtendedMappingSchema,
    ExtendedSchemaNode,
    ExtendedSequenceSchema,
    ExtendedString as String,
    PermissiveMappingSchema,
    # below XML object is useful to define XML schemas that OpenAPI v3 also supports!
    # it adds support for 'attributes', 'prefix', 'namespace'  an other keywords specific to XML
    XMLObject
)

# convenience definitions to make it quicker for developers not to reinvent the wheel
from cornice_swagger.common import (
    FileLocal,
    FileURL,
    URL,
    UUID,
    SLUG,
    # extra validators
    OneOfEnum as OneOf,    # exactly the same as 'colander.OneOf', but also accepts direct Enum as input
    OneOfCaseInsensitive,  # ignore case for matching a string
    SemanticVersion,  # <major>.<minor>.<patch> strings
    StringRange,  # just like range, but can use numerical strings
)


##################################################################################################################
# Examples
#   Load contents with file names as keys for easier reference later in examples.
#   Examples are used to provide explicit content of a request or response body.
##################################################################################################################

SCHEMA_EXAMPLE_DIR = os.path.join(os.path.dirname(__file__), "schema-examples")
EXAMPLES = {}
for name in os.listdir(SCHEMA_EXAMPLE_DIR):
    path = os.path.join(SCHEMA_EXAMPLE_DIR, name)
    ext = os.path.splitext(name)[-1]
    with open(path, "r") as f:
        if ext in [".json", ".yaml", ".yml"]:
            EXAMPLES[name] = {"path": path, "data": yaml.safe_load(f)}  # both JSON/YAML
        else:
            EXAMPLES[name] = {"path": path, "data": f.read()}  # raw content (text value, XML)


##################################################################################################################
# API tags and metadata
##################################################################################################################

API_TITLE = "OpenAPI Demo"
API_INFO = {
    "description": "Demo using OpenAPI v3 schemas.",
    "contact": {"name": "Best Developer", "email": "nowhere@email.com", "url": "https://my-source-repo.git"}
}
API_DOCS = {
    "description": "{} documentation".format(API_TITLE),
    "url": "https://some-read-the-docs.html"
}

TAG_API = "API"
TAG_JOBS = "Jobs"
TAG_PROCESSES = "Processes"
TAG_DEPRECATED = "Deprecated Endpoints"

##################################################################################################################
# API endpoints
# These "services" are wrappers that allow Cornice to generate the JSON API
##################################################################################################################

api_frontpage_service = Service(name="api_frontpage", path="/")
api_openapi_ui_service = Service(name="api_openapi_ui", path="/api")
openapi_json_service = Service(name="openapi_json", path="/json")

jobs_service = Service(name="jobs", path="/jobs")
job_service = Service(name="job", path=jobs_service.path + "/{job_id}")

processes_service = Service(name="processes", path="/processes")
process_service = Service(name="process", path=processes_service.path + "/{process_id}")

xml_service = Service(name="xml", path="/xml")


##################################################################################################################
# Repetitive constants / enum
#   Those can be used to generate validators and more specific schema types, 
#   while using them for other code operations in the API implementation. 
##################################################################################################################

class ContentType(enum.Enum):
    APP_JSON = "application/json"
    APP_XML = "application/xml"
    TXT_XML = "text/xml"
    TXT_HTML = "text/html"
    TXT_PLAIN = "text/plain"
    ANY = "*/*"


class AcceptLanguage(enum.Enum):
    EN_CA = "en-CA"
    EN_US = "en-US"
    FR_CA = "fr-CA"


class JobStatuses(enum.Enum):
    """Statuses of jobs execution."""
    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"


class Sorting(enum.Enum):
    """Sorting methods of jobs."""
    ASCENDING = "asc"
    DESCENDING = "desc"


##################################################################################################################
# Generic schemas
##################################################################################################################


class ReferenceURL(AnyOfKeywordSchema):
    _any_of = [
        FileURL(),
        FileLocal(),
        URL(),  # least restrictive format must be last so that validators of previous fail/match them before
    ]


class AnyIdentifier(SLUG):
    pass


class ProcessIdentifier(AnyOfKeywordSchema):
    description = "Process identifier."
    _any_of = [
        # UUID first because more strict than SLUG, and SLUG can be similar to UUID, but in the end any is valid
        UUID(description="Unique identifier."),
        SLUG(description="Generic identifier. This is a user-friendly slug-name to retrieve the process.", title="ID"),
    ]


class Version(ExtendedSchemaNode):
    # note: internally use LooseVersion, so don't be too strict about pattern
    schema_type = String
    description = "Version string."
    example = "1.2.3"
    validator = SemanticVersion()


class ContentTypeHeader(ExtendedSchemaNode):
    # ok to use 'name' in this case because target 'key' in the mapping must
    # be that specific value but cannot have a field named with this format
    name = "Content-Type"
    schema_type = String


# we can define Enums schemas from real Python Enum definitions
# two variants are possible, both will result in corresponding 'enum' values when generating the OpenAPI schemas


class AcceptHeader(ExtendedSchemaNode):
    name = "Accept"  # see above
    enum_cls = ContentType
    schema_type = Enum  # in this case, we employ the 'colander.Enum' approach to populate allowed members
    attr = "value"  # default is to use 'name', but we use the 'value'
    missing = drop
    default = ContentType.APP_JSON.value  # must be one of the 'ContentType' enum, or it will raise at creation


class AcceptLanguageHeader(ExtendedSchemaNode):
    name = "Accept-Language"  # see above
    schema_type = String  # In this case, we use the String/Validator approach. Result will be similar to above
    validator = OneOf(AcceptLanguage)  # values are used automatically, otherwise pass 'attr="name"'
    missing = drop
    default = AcceptLanguage.EN_CA.value  # again, must be one of the real values, or fails at instantiation time


class JsonHeader(ExtendedMappingSchema):
    content_type = ContentTypeHeader(example=ContentType.APP_XML.value, default=ContentType.APP_XML.value)


class HtmlHeader(ExtendedMappingSchema):
    content_type = ContentTypeHeader(example=ContentType.TXT_HTML.value, default=ContentType.TXT_HTML.value)


class XmlHeader(ExtendedMappingSchema):
    content_type = ContentTypeHeader(example=ContentType.APP_XML.value, default=ContentType.APP_XML.value)


class RequestContentTypeHeader(OneOfKeywordSchema):
    _one_of = [
        JsonHeader(),
        XmlHeader(),
    ]


class ResponseContentTypeHeader(OneOfKeywordSchema):
    _one_of = [
        JsonHeader(),
        XmlHeader(),
        HtmlHeader(),
    ]


class RequestHeaders(RequestContentTypeHeader):
    """Headers that can indicate how to adjust the behavior and/or result the be provided in the response."""
    accept = AcceptHeader()
    accept_language = AcceptLanguageHeader()


class ResponseHeaders(ResponseContentTypeHeader):
    """Headers describing resulting response."""


class RedirectHeaders(ResponseHeaders):
    Location = ExtendedSchemaNode(String(), example="https://job/123/result", description="Redirect resource location.")


class NoContent(ExtendedMappingSchema):
    description = "Empty response body."
    default = {}


class KeywordList(ExtendedSequenceSchema):
    keyword = ExtendedSchemaNode(String())


class Language(ExtendedSchemaNode):
    schema_type = String
    example = AcceptLanguage.EN_CA.value
    validator = OneOf(AcceptLanguage)


class ValueLanguage(ExtendedMappingSchema):
    lang = Language(missing=drop, description="Language of the value content.")


class LinkLanguage(ExtendedMappingSchema):
    hreflang = Language(missing=drop, description="Language of the content located at the link.")


class MetadataBase(ExtendedMappingSchema):
    type = ExtendedSchemaNode(String(), missing=drop)
    title = ExtendedSchemaNode(String(), missing=drop)


class MetadataRole(ExtendedMappingSchema):
    role = URL(missing=drop)


class LinkRelationship(ExtendedMappingSchema):
    rel = SLUG(description="Relationship of the link to the current content.")


class LinkBase(LinkLanguage, MetadataBase):
    href = URL(description="Hyperlink reference.")


class Link(LinkRelationship, LinkBase):
    pass


class MetadataValue(NotKeywordSchema, ValueLanguage, MetadataBase):
    _not = [
        # make sure value metadata does not allow 'rel' and 'hreflang' reserved for link reference
        # explicitly refuse them such that when an href/rel link is provided, only link details are possible
        LinkRelationship(description="Field 'rel' must refer to a link reference with 'href'."),
        LinkLanguage(description="Field 'hreflang' must refer to a link reference with 'href'."),
    ]
    value = ExtendedSchemaNode(String(), description="Plain text value of the information.")


class MetadataContent(OneOfKeywordSchema):
    _one_of = [
        Link(title="MetadataLink"),
        MetadataValue(),
    ]


class Metadata(MetadataContent, MetadataRole):
    pass


class MetadataList(ExtendedSequenceSchema):
    metadata = Metadata()


class LinkList(ExtendedSequenceSchema):
    description = "List of links relative to the applicable object."
    title = "Links"
    link = Link()


class LandingPage(ExtendedMappingSchema):
    links = LinkList()


class Format(ExtendedMappingSchema):
    title = "Format"
    mimeType = ExtendedSchemaNode(String())
    schema = ExtendedSchemaNode(String(), missing=drop)
    encoding = ExtendedSchemaNode(String(), missing=drop)


class FormatDefault(Format):
    """Format for process input are assumed plain text if the MIME-type was omitted and is not
    one of the known formats by this instance. When executing a job, the best match will be used
    to run the process, and will fallback to the default as last resort.
    """
    mimeType = ExtendedSchemaNode(String(), default=ContentType.TXT_PLAIN, example=ContentType.APP_XML.value)


class FormatExtra(ExtendedMappingSchema):
    maximumMegabytes = ExtendedSchemaNode(Integer(), missing=drop)


class FormatDescription(FormatDefault, FormatExtra):
    default = ExtendedSchemaNode(
        Boolean(), missing=drop, default=False,
        description=(
            "Indicates if this format should be considered as the default one in case none of the other "
            "allowed or supported formats was matched nor provided as input during job submission."
        )
    )


class FormatMedia(FormatExtra):
    """Format employed to represent data MIME-type schemas."""
    mediaType = ExtendedSchemaNode(String())
    schema = ExtendedSchemaNode(String(), missing=drop)
    encoding = ExtendedSchemaNode(String(), missing=drop)


class FormatDescriptionList(ExtendedSequenceSchema):
    format = FormatDescription()


class AdditionalParameterValuesList(ExtendedSequenceSchema):
    values = ExtendedSchemaNode(String())


class AdditionalParameter(ExtendedMappingSchema):
    name = ExtendedSchemaNode(String())
    values = AdditionalParameterValuesList()


class AdditionalParameterList(ExtendedSequenceSchema):
    additionalParameter = AdditionalParameter()


class AdditionalParametersMeta(LinkBase, MetadataRole):
    pass


class AdditionalParameters(ExtendedMappingSchema):
    parameters = AdditionalParameterList()


class AdditionalParametersItem(AnyOfKeywordSchema):
    _any_of = [
        AdditionalParametersMeta(missind=drop),
        AdditionalParameters()
    ]


class AdditionalParametersList(ExtendedSequenceSchema):
    additionalParameter = AdditionalParametersItem()


class Content(ExtendedMappingSchema):
    href = ReferenceURL(description="URL to file.", title="AppContentURL",
                        default=drop,       # if invalid, drop it completely,
                        missing=required,   # but still mark as 'required' for parent objects
                        example="http://some.host/path/somefile.json")


class Offering(ExtendedMappingSchema):
    code = ExtendedSchemaNode(String(), missing=drop, description="Descriptor of represented information in 'content'.")
    content = Content()


class AppContext(ExtendedMappingSchema):
    description = "OGC Web Service definition from an URL reference."
    title = "AppContext"
    offering = Offering()


class DescriptionBase(ExtendedMappingSchema):
    title = ExtendedSchemaNode(String(), missing=drop, description="Short name definition of the process.")
    abstract = ExtendedSchemaNode(String(), missing=drop, description="Detailed explanation of the process operation.")
    links = LinkList(missing=drop, description="References to endpoints with information related to the process.")


class DescriptionApp(ExtendedMappingSchema):
    AppContext = AppContext(missing=drop)


class DescriptionExtra(ExtendedMappingSchema):
    additionalParameters = AdditionalParametersList(missing=drop)


class DescriptionType(DescriptionBase, DescriptionExtra):
    pass


class ProcessDescriptionMeta(ExtendedMappingSchema):
    # employ empty lists by default if nothing is provided for process description
    keywords = KeywordList(
        default=[],
        description="Keywords applied to the process for search and categorization purposes.")
    metadata = MetadataList(
        default=[],
        description="External references to documentation or metadata sources relevant to the process.")


class ProcessDeployMeta(ExtendedMappingSchema):
    # don't require fields at all for process deployment, default to empty if omitted
    keywords = KeywordList(
        missing=drop,
        default=[],
        description="Keywords applied to the process for search and categorization purposes.")
    metadata = MetadataList(
        missing=drop,
        default=[],
        description="External references to documentation or metadata sources relevant to the process.")


class InputOutputDescriptionMeta(ExtendedMappingSchema):
    # remove unnecessary empty lists by default if nothing is provided for inputs/outputs
    def __init__(self, *args, **kwargs):
        super(InputOutputDescriptionMeta, self).__init__(*args, **kwargs)
        for child in self.children:
            if child.name in ["keywords", "metadata"]:
                child.missing = drop


class MinOccursDefinition(OneOfKeywordSchema):
    description = "Minimum amount of values required for this input."
    title = "MinOccurs"
    example = 1
    _one_of = [
        ExtendedSchemaNode(Integer(), validator=Range(min=0),
                           description="Positive integer."),
        ExtendedSchemaNode(String(), validator=StringRange(min=0), pattern="^[0-9]+$",
                           description="Numerical string representing a positive integer."),
    ]


class MaxOccursDefinition(OneOfKeywordSchema):
    description = "Maximum amount of values allowed for this input."
    title = "MaxOccurs"
    example = 1
    _one_of = [
        ExtendedSchemaNode(Integer(), validator=Range(min=0),
                           description="Positive integer."),
        ExtendedSchemaNode(String(), validator=StringRange(min=0), pattern="^[0-9]+$",
                           description="Numerical string representing a positive integer."),
        ExtendedSchemaNode(String(), validator=OneOf(["unbounded"])),
    ]


class WithMinMaxOccurs(ExtendedMappingSchema):
    minOccurs = MinOccursDefinition(missing=drop)
    maxOccurs = MaxOccursDefinition(missing=drop)


class ProcessDescriptionType(DescriptionType, DescriptionApp):
    id = ProcessIdentifier()
    version = Version(missing=drop)
    created = ExtendedSchemaNode(DateTime(), description="Creation date and time of the quote in ISO-8601 format.")


class InputIdentifierType(ExtendedMappingSchema):
    id = AnyIdentifier(description="Identifier of the input.")


class OutputIdentifierType(ExtendedMappingSchema):
    id = AnyIdentifier(description="Identifier of the output.")


class InputDescriptionType(InputIdentifierType, DescriptionType, InputOutputDescriptionMeta):
    pass


class OutputDescriptionType(OutputIdentifierType, DescriptionType, InputOutputDescriptionMeta):
    pass


class WithFormats(ExtendedMappingSchema):
    formats = FormatDescriptionList()


class ComplexInputType(WithFormats):
    pass


class SupportedCRS(ExtendedMappingSchema):
    crs = URL(title="CRS", description="Coordinate Reference System")
    default = ExtendedSchemaNode(Boolean(), missing=drop)


class SupportedCRSList(ExtendedSequenceSchema):
    crs = SupportedCRS(title="SupportedCRS")


class BoundingBoxInputType(ExtendedMappingSchema):
    supportedCRS = SupportedCRSList()


class LiteralReference(ExtendedMappingSchema):
    reference = ReferenceURL()


class NameReferenceType(ExtendedMappingSchema):
    name = ExtendedSchemaNode(String())
    reference = ReferenceURL(missing=drop)


class DataTypeSchema(NameReferenceType):
    description = "Type of the literal data representation."
    title = "DataType"


class UomSchema(NameReferenceType):
    title = "UnitOfMeasure"


class AllowedValuesList(ExtendedSequenceSchema):
    allowedValues = ExtendedSchemaNode(String())


class AllowedValues(ExtendedMappingSchema):
    allowedValues = AllowedValuesList()


class AllowedRange(ExtendedMappingSchema):
    minimumValue = ExtendedSchemaNode(String(), missing=drop)
    maximumValue = ExtendedSchemaNode(String(), missing=drop)
    spacing = ExtendedSchemaNode(String(), missing=drop)
    rangeClosure = ExtendedSchemaNode(String(), missing=drop,
                                      validator=OneOf(["closed", "open", "open-closed", "closed-open"]))


class AllowedRangesList(ExtendedSequenceSchema):
    allowedRanges = AllowedRange()


class AllowedRanges(ExtendedMappingSchema):
    allowedRanges = AllowedRangesList()


class AnyValue(ExtendedMappingSchema):
    anyValue = ExtendedSchemaNode(Boolean(), missing=drop, default=True)


class ValuesReference(ExtendedMappingSchema):
    valueReference = ReferenceURL()


class AnyLiteralType(OneOfKeywordSchema):
    """
    .. seealso::
        - :class:`AnyLiteralDataType`
        - :class:`AnyLiteralValueType`
        - :class:`AnyLiteralDefaultType`
    """
    _one_of = [
        ExtendedSchemaNode(Float()),
        ExtendedSchemaNode(Integer()),
        ExtendedSchemaNode(Boolean()),
        ExtendedSchemaNode(String()),
    ]


class AnyLiteralDataType(ExtendedMappingSchema):
    data = AnyLiteralType()


class AnyLiteralValueType(ExtendedMappingSchema):
    value = AnyLiteralType()


class AnyLiteralDefaultType(ExtendedMappingSchema):
    default = AnyLiteralType()


class LiteralDataDomainDefinition(ExtendedMappingSchema):
    default = AnyLiteralDefaultType()
    defaultValue = ExtendedSchemaNode(String(), missing=drop)
    dataType = DataTypeSchema(missing=drop)
    uom = UomSchema(missing=drop)


class LiteralDataDomainConstraints(OneOfKeywordSchema, LiteralDataDomainDefinition):
    _one_of = [
        AllowedValues,
        AllowedRanges,
        ValuesReference,
        AnyValue,  # must be last because it"s the most permissive (always valid, default)
    ]


class LiteralDataDomainList(ExtendedSequenceSchema):
    literalDataDomain = LiteralDataDomainConstraints()


class LiteralInputType(NotKeywordSchema, ExtendedMappingSchema):
    _not = [
        WithFormats,
    ]
    literalDataDomains = LiteralDataDomainList(missing=drop)


class InputTypeDefinition(OneOfKeywordSchema):
    _one_of = [
        # NOTE:
        #   LiteralInputType could be used to represent a complex input if the 'format' is missing in
        #   process deployment definition but is instead provided in CWL definition.
        #   This use case is still valid because 'format' can be inferred from the combining Process/CWL contents.
        BoundingBoxInputType,
        ComplexInputType,  # should be 2nd to last because very permissive, but requires format at least
        LiteralInputType,  # must be last because it"s the most permissive (all can default if omitted)
    ]


class InputType(AnyOfKeywordSchema):
    _any_of = [
        InputDescriptionType(),
        InputTypeDefinition(),
        WithMinMaxOccurs(),
    ]


class InputTypeList(ExtendedSequenceSchema):
    input = InputType()


class LiteralOutputType(NotKeywordSchema, ExtendedMappingSchema):
    _not = [
        WithFormats,
    ]
    literalDataDomains = LiteralDataDomainList(missing=drop)


class BoundingBoxOutputType(ExtendedMappingSchema):
    supportedCRS = SupportedCRSList()


class ComplexOutputType(WithFormats):
    pass


class OutputTypeDefinition(OneOfKeywordSchema):
    _one_of = [
        BoundingBoxOutputType,
        ComplexOutputType,  # should be 2nd to last because very permissive, but requires format at least
        LiteralOutputType,  # must be last because it's the most permissive (all can default if omitted)
    ]


class OutputType(AnyOfKeywordSchema):
    _any_of = [
        OutputTypeDefinition(),
        OutputDescriptionType(),
    ]


class OutputDescriptionList(ExtendedSequenceSchema):
    output = OutputType()


class JobStatusEnum(ExtendedSchemaNode):
    schema_type = String
    title = "JobStatus"
    default = JobStatuses.ACCEPTED.value
    example = JobStatuses.SUCCESS.value
    validator = OneOf(JobStatuses)


class JobSortEnum(ExtendedSchemaNode):
    schema_type = String
    title = "JobSortingMethod"
    default = Sorting.ASCENDING.value
    example = Sorting.ASCENDING.value
    validator = OneOf(Sorting)


##################################################################################################################
# XML schemas
#   OpenAPI v3 supports XML object definitions, with attributes, namespaces and prefixes
#   Those are also supported by cornice-swagger, using 'XMLObject' schema as base.
#   See its documentation for more details about each attribute it supports.
##################################################################################################################

class XMLNamespace(XMLObject):
    prefix = "xml"


class AppNamespace(XMLObject):
    """Custom namespace for demo app.

    All XML object classes that inherit from this schema will be generated with the corresponding prefix.
    For example, class named ``Example`` would be with XML namespace ``app:Example``,
    where ``app`` prefix would correspond to XML namespace located at below URL.
    """
    prefix = "app"
    namespace = "https://www.demo-app.com/schemas"


class XMLReferenceAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    attribute = True
    name = "href"
    prefix = "xlink"
    format = "url"


class MimeTypeAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    attribute = True
    name = "mimeType"
    prefix = drop
    example = ContentType.APP_XML.value


class EncodingAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    attribute = True
    name = "encoding"
    prefix = drop
    example = "UTF-8"


class AppVersion(ExtendedSchemaNode, AppNamespace):
    schema_type = String
    name = "Version"
    default = "1.0.0"
    example = "1.0.0"


class AppAcceptVersions(ExtendedSequenceSchema, AppNamespace):
    description = "Accepted versions to produce the response."
    name = "AcceptVersions"
    item = AppVersion()


class AppLanguage(ExtendedSchemaNode, AppNamespace):
    description = "Desired language to produce the response."
    schema_type = String
    name = "Language"
    default = AcceptLanguage.EN_US.value
    example = AcceptLanguage.EN_CA.value


class LanguageAttribute(AppLanguage):
    description = "RFC-4646 language code of the human-readable text."
    name = "language"
    attribute = True


class AppVersionAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "version"
    attribute = True
    default = "1.0.0"
    example = "1.0.0"


class AppLanguageAttribute(ExtendedSchemaNode, XMLNamespace):
    schema_type = String
    name = "lang"
    attribute = True
    default = AcceptLanguage.EN_US.value
    example = AcceptLanguage.EN_CA.value


class AppParameters(ExtendedMappingSchema):
    service = ExtendedSchemaNode(String(), example="App", description="Service selection.",
                                 validator=OneOfCaseInsensitive(["App"]))
    request = ExtendedSchemaNode(String(), example="GetCapabilities", description="App operation to accomplish",
                                 validator=OneOfCaseInsensitive(["GetCapabilities", "DescribeProcess", "Execute"]))
    version = Version(exaple="1.0.0", default="1.0.0", validator=OneOf(["1.0.0", "2.0.0", "2.0"]))
    identifier = ExtendedSchemaNode(String(), exaple="hello", missing=drop,
                                    example="example-process,another-process",
                                    description="Single or comma-separated list of process identifiers to describe, "
                                                "and single one for execution.")
    data_inputs = ExtendedSchemaNode(String(), name="DataInputs", missing=drop,
                                     example="message=hi&names=user1,user2&value=1",
                                     description="Process execution inputs provided as Key-Value Pairs (KVP).")


class AppOperationGetNoContent(ExtendedMappingSchema):
    description = "No content body provided (GET requests)."
    default = {}


class AppOperationPost(ExtendedMappingSchema):
    accepted_versions = AppAcceptVersions(missing=drop, default="1.0.0")
    language = AppLanguageAttribute(missing=drop)


class AppGetCapabilitiesPost(AppOperationPost, AppNamespace):
    name = "GetCapabilities"
    title = "GetCapabilities"


class AppIdentifier(ExtendedSchemaNode, AppNamespace):
    schema_type = String
    name = "Identifier"


class AppIdentifierList(ExtendedSequenceSchema, AppNamespace):
    name = "Identifiers"
    item = AppIdentifier()


class AppTitle(ExtendedSchemaNode, AppNamespace):
    schema_type = String
    name = "Title"


class AppAbstract(ExtendedSchemaNode, AppNamespace):
    schema_type = String
    name = "Abstract"


class AppMetadataLink(ExtendedSchemaNode, XMLObject):
    schema_name = "Metadata"
    schema_type = String
    attribute = True
    name = "Metadata"
    prefix = "xlink"
    example = "App"
    wrapped = False  # metadata xlink at same level as other items


class AppMetadata(ExtendedSequenceSchema, AppNamespace):
    schema_type = String
    name = "Metadata"
    title = AppMetadataLink(missing=drop)


class AppDescribeProcessPost(AppOperationPost, AppNamespace):
    name = "DescribeProcess"
    title = "DescribeProcess"
    identifier = AppIdentifierList(
        description="Single or comma-separated list of process identifier to describe.",
        example="example"
    )


class AppExecuteDataInputs(ExtendedMappingSchema, AppNamespace):
    description = "XML data inputs provided for App POST request (Execute)."
    name = "DataInputs"
    title = "DataInputs"


class AppExecutePost(AppOperationPost, AppNamespace):
    name = "Execute"
    title = "Execute"
    identifier = AppIdentifier(description="Identifier of the process to execute with data inputs.")
    dataInputs = AppExecuteDataInputs(description="Data inputs to be provided for process execution.")


class AppRequestBody(OneOfKeywordSchema):
    _one_of = [
        AppExecutePost(),
        AppDescribeProcessPost(),
        AppGetCapabilitiesPost(),
    ]
    examples = {
        "Execute": {
            "summary": "Execute request example.",
            "value": EXAMPLES["wps_execute_request.xml"]["data"]
        }
    }


class AppHeaders(ExtendedMappingSchema):
    accept = AcceptHeader(missing=drop)


class AppEndpointGet(ExtendedMappingSchema):
    header = AppHeaders()
    querystring = AppParameters()
    body = AppOperationGetNoContent(missing=drop)


class AppEndpointPost(ExtendedMappingSchema):
    header = AppHeaders()
    body = AppRequestBody()


class XMLBooleanAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = Boolean
    attribute = True


class XMLString(ExtendedSchemaNode, XMLObject):
    schema_type = String


class AppString(ExtendedSchemaNode, AppNamespace):
    schema_type = String


class AppKeywordList(ExtendedSequenceSchema, AppNamespace):
    title = "AppKeywords"
    keyword = AppString(name="Keyword", title="AppKeyword", example="Weaver")


class AppType(ExtendedMappingSchema, AppNamespace):
    schema_type = String
    name = "Type"
    example = "theme"
    additionalProperties = {
        "codeSpace": {
            "type": "string",
            "example": "ISOTC211/19115",
            "xml": {"attribute": True}
        }
    }


class AppPhone(ExtendedMappingSchema, AppNamespace):
    name = "Phone"
    voice = AppString(name="Voice", title="AppVoice", example="1-234-567-8910", missing=drop)
    facsimile = AppString(name="Facsimile", title="AppFacsimile", missing=drop)


class AppAddress(ExtendedMappingSchema, AppNamespace):
    name = "Address"
    delivery_point = AppString(name="DeliveryPoint", title="AppDeliveryPoint",
                               example="123 Place Street", missing=drop)
    city = AppString(name="City", title="AppCity", example="Nowhere", missing=drop)
    country = AppString(name="Country", title="AppCountry", missing=drop)
    admin_area = AppString(name="AdministrativeArea", title="AdministrativeArea", missing=drop)
    postal_code = AppString(name="PostalCode", title="AppPostalCode", example="A1B 2C3", missing=drop)
    email = AppString(name="ElectronicMailAddress", title="AppElectronicMailAddress",
                      example="mail@me.com", validator=Email, missing=drop)


class AppContactInfo(ExtendedMappingSchema, AppNamespace):
    name = "ContactInfo"
    phone = AppPhone(missing=drop)
    address = AppAddress(missing=drop)


class AppServiceContact(ExtendedMappingSchema, AppNamespace):
    name = "ServiceContact"
    individual = AppString(name="IndividualName", title="AppIndividualName", example="John Smith", missing=drop)
    position = AppString(name="PositionName", title="AppPositionName", example="One Man Team", missing=drop)
    contact = AppContactInfo(missing=drop, default={})


class AppServiceProvider(ExtendedMappingSchema, AppNamespace):
    description = "Details about the institution providing the service."
    name = "ServiceProvider"
    title = "ServiceProvider"
    provider_name = AppString(name="ProviderName", title="AppProviderName", example="EXAMPLE")
    provider_site = AppString(name="ProviderName", title="AppProviderName", example="http://schema-example.com")
    contact = AppServiceContact(required=False, defalult={})


class AppDescriptionType(ExtendedMappingSchema, AppNamespace):
    name = "DescriptionType"
    # below '_title' is to avoid conflict with 'title' that is employed by schema classes to generate their '$ref'
    _title = AppTitle(description="Title of the service.", example="Weaver")
    abstract = AppAbstract(description="Detail about the service.", example="Weaver App example schema.", missing=drop)
    metadata = AppMetadata(description="Metadata of the service.", example="Weaver App example schema.", missing=drop)


class AppServiceIdentification(AppDescriptionType, AppNamespace):
    name = "ServiceIdentification"
    title = "ServiceIdentification"
    keywords = AppKeywordList(name="Keywords")
    type = AppType()
    svc_type = AppString(name="ServiceType", title="ServiceType", example="App")
    svc_type_ver1 = AppString(name="ServiceTypeVersion", title="ServiceTypeVersion", example="1.0.0")
    svc_type_ver2 = AppString(name="ServiceTypeVersion", title="ServiceTypeVersion", example="2.0.0")
    fees = AppString(name="Fees", title="Fees", example="NONE", missing=drop, default="NONE")
    access = AppString(name="AccessConstraints", title="AccessConstraints",
                       example="NONE", missing=drop, default="NONE")
    provider = AppServiceProvider()


class AppOperationName(ExtendedSchemaNode, AppNamespace):
    schema_type = String
    attribute = True
    name = "name"
    example = "GetCapabilities"
    validator = OneOf(["GetCapabilities", "DescribeProcess", "Execute"])


class OperationLink(ExtendedSchemaNode, XMLObject):
    schema_type = String
    attribute = True
    name = "href"
    prefix = "xlink"
    example = "http://schema-example.com/App"


class OperationRequest(ExtendedMappingSchema, AppNamespace):
    href = OperationLink()


class AppHTTP(ExtendedMappingSchema, AppNamespace):
    get = OperationRequest(name="Get", title="AppGet")
    post = OperationRequest(name="Post", title="AppPost")


class AppDCP(ExtendedMappingSchema, AppNamespace):
    http = AppHTTP(name="HTTP", missing=drop)
    https = AppHTTP(name="HTTPS", missing=drop)


class Operation(ExtendedMappingSchema, AppNamespace):
    name = AppOperationName()
    dcp = AppDCP()


class OperationsMetadata(ExtendedSequenceSchema, AppNamespace):
    name = "OperationsMetadata"
    op = Operation()


class ProcessVersion(ExtendedSchemaNode, AppNamespace):
    schema_type = String
    attribute = True


class AppProcessSummary(ExtendedMappingSchema, AppNamespace):
    name = "Process"
    title = "Process"
    _title = AppTitle(example="Example Process", description="Title of the process.")
    version = ProcessVersion(name="processVersion", default="None", example="1.2",
                             description="Version of the corresponding process summary.")
    identifier = AppIdentifier(example="example", description="Identifier to refer to the process.")
    abstract = AppAbstract(example="Process for example schema.", description="Detail about the process.")


class AppProcessOfferings(ExtendedSequenceSchema, AppNamespace):
    name = "ProcessOfferings"
    title = "ProcessOfferings"
    process = AppProcessSummary(name="Process")


class AppLanguagesType(ExtendedSequenceSchema, AppNamespace):
    title = "LanguagesType"
    wrapped = False
    lang = AppLanguage(name="Language")


class AppLanguageSpecification(ExtendedMappingSchema, AppNamespace):
    name = "Languages"
    title = "Languages"
    default = AppLanguage(name="Default")
    supported = AppLanguagesType(name="Supported")


class AppResponseBaseType(PermissiveMappingSchema, AppNamespace):
    version = AppVersionAttribute()
    lang = AppLanguageAttribute()


class AppProcessVersion(ExtendedSchemaNode, AppNamespace):
    schema_type = String
    description = "Release version of this Process."
    name = "processVersion"
    attribute = True


class AppInputDescriptionType(AppDescriptionType):
    identifier = AppIdentifier(description="Unique identifier of the input.")
    # override below to have different examples/descriptions
    _title = AppTitle(description="Human readable representation of the process input.")
    abstract = AppAbstract(missing=drop)
    metadata = AppMetadata(missing=drop)


class AppLiteralInputType(ExtendedMappingSchema, XMLObject):
    pass


class AppLiteralData(AppLiteralInputType):
    name = "LiteralData"


class AppCRSsType(ExtendedMappingSchema, AppNamespace):
    crs = XMLString(name="CRS", description="Coordinate Reference System")


class AppSupportedCRS(ExtendedSequenceSchema):
    crs = AppCRSsType(name="CRS")


class AppSupportedCRSType(ExtendedMappingSchema, AppNamespace):
    name = "SupportedCRSsType"
    default = AppCRSsType(name="Default")
    supported = AppSupportedCRS(name="Supported")


class AppBoundingBoxData(ExtendedMappingSchema, XMLObject):
    data = AppSupportedCRSType(name="BoundingBoxData")


class AppFormatDefinition(ExtendedMappingSchema, XMLObject):
    mime_type = XMLString(name="MimeType", default=ContentType.TXT_PLAIN, example=ContentType.TXT_PLAIN)
    encoding = XMLString(name="Encoding", missing=drop, example="base64")
    schema = XMLString(name="Schema", missing=drop)


class AppFileFormat(ExtendedMappingSchema, XMLObject):
    name = "Format"
    format = AppFormatDefinition()


class AppFormatList(ExtendedSequenceSchema):
    format = AppFileFormat()


class AppComplexInputType(ExtendedMappingSchema, AppNamespace):
    max_mb = XMLString(name="maximumMegabytes", attribute=True)
    defaults = AppFileFormat(name="Default")
    supported = AppFormatList(name="Supported")


class AppComplexData(ExtendedMappingSchema, XMLObject):
    data = AppComplexInputType(name="ComplexData")


class AppInputFormChoice(OneOfKeywordSchema):
    title = "InputFormChoice"
    _one_of = [
        AppComplexData(),
        AppLiteralData(),
        AppBoundingBoxData(),
    ]


class AppMinOccursAttribute(MinOccursDefinition, XMLObject):
    name = "minOccurs"
    attribute = True


class AppMaxOccursAttribute(MinOccursDefinition, XMLObject):
    name = "maxOccurs"
    prefix = drop
    attribute = True


class AppDataInputDescription(ExtendedMappingSchema):
    min_occurs = AppMinOccursAttribute()
    max_occurs = AppMaxOccursAttribute()


class AppDataInputItem(AllOfKeywordSchema, AppNamespace):
    _all_of = [
        AppInputDescriptionType(),
        AppInputFormChoice(),
        AppDataInputDescription(),
    ]


class AppDataInputs(ExtendedSequenceSchema, AppNamespace):
    name = "DataInputs"
    title = "DataInputs"
    input = AppDataInputItem()


class AppOutputDescriptionType(AppDescriptionType):
    name = "OutputDescriptionType"
    title = "OutputDescriptionType"
    identifier = AppIdentifier(description="Unique identifier of the output.")
    # override below to have different examples/descriptions
    _title = AppTitle(description="Human readable representation of the process output.")
    abstract = AppAbstract(missing=drop)
    metadata = AppMetadata(missing=drop)


class ProcessOutputs(ExtendedSequenceSchema, AppNamespace):
    name = "ProcessOutputs"
    title = "ProcessOutputs"
    output = AppOutputDescriptionType()


class AppGetCapabilities(AppResponseBaseType):
    name = "Capabilities"
    title = "Capabilities"  # not to be confused by 'GetCapabilities' used for request
    svc = AppServiceIdentification()
    ops = OperationsMetadata()
    offering = AppProcessOfferings()
    languages = AppLanguageSpecification()


class AppProcessDescriptionType(AppResponseBaseType, AppProcessVersion):
    name = "ProcessDescriptionType"
    description = "Description of the requested process by identifier."
    store = XMLBooleanAttribute(name="storeSupported", example=True, default=True)
    status = XMLBooleanAttribute(name="statusSupported", example=True, default=True)
    inputs = AppDataInputs()
    outputs = ProcessOutputs()


class AppProcessDescriptionList(ExtendedSequenceSchema, AppNamespace):
    name = "ProcessDescriptions"
    title = "ProcessDescriptions"
    description = "Listing of process description for every requested identifier."
    wrapped = False
    process = AppProcessDescriptionType()


class AppDescribeProcess(AppResponseBaseType):
    name = "DescribeProcess"
    title = "DescribeProcess"
    process = AppProcessDescriptionList()


class AppStatusLocationAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "statusLocation"
    prefix = drop
    attribute = True
    format = "file"


class AppServiceInstanceAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "serviceInstance"
    prefix = drop
    attribute = True
    format = "url"


class CreationTimeAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = DateTime
    name = "creationTime"
    title = "CreationTime"
    prefix = drop
    attribute = True


class AppStatusSuccess(ExtendedSchemaNode, AppNamespace):
    schema_type = String
    name = "ProcessSucceeded"
    title = "ProcessSucceeded"


class AppStatusFailed(ExtendedSchemaNode, AppNamespace):
    schema_type = String
    name = "ProcessFailed"
    title = "ProcessFailed"


class AppStatus(ExtendedMappingSchema, AppNamespace):
    name = "Status"
    title = "Status"
    creationTime = CreationTimeAttribute()
    status_success = AppStatusSuccess(missing=drop)
    status_failed = AppStatusFailed(missing=drop)


class AppOutputBase(ExtendedMappingSchema):
    identifier = AppIdentifier()
    _title = AppTitle()
    abstract = AppAbstract(missing=drop)


class AppOutputDefinitionItem(AppOutputBase, AppNamespace):
    name = "Output"
    # use different title to avoid OpenAPI schema definition clash with 'Output' of 'AppProcessOutputs'
    title = "OutputDefinition"


class AppOutputDefinitions(ExtendedSequenceSchema, AppNamespace):
    name = "OutputDefinitions"
    title = "OutputDefinitions"
    out_def = AppOutputDefinitionItem()


class AppOutputLiteral(ExtendedMappingSchema):
    data = ()


class AppReference(ExtendedMappingSchema, AppNamespace):
    href = XMLReferenceAttribute()
    mimeType = MimeTypeAttribute()
    encoding = EncodingAttribute()


class AppOutputReference(ExtendedMappingSchema):
    title = "OutputReference"
    reference = AppReference(name="Reference")


class AppOutputData(OneOfKeywordSchema):
    _one_of = [
        AppOutputLiteral(),
        AppOutputReference(),
    ]


class AppDataOutputItem(AllOfKeywordSchema, AppNamespace):
    name = "Output"
    # use different title to avoid OpenAPI schema definition clash with 'Output' of 'AppOutputDefinitions'
    title = "DataOutput"
    _all_of = [
        AppOutputBase(),
        AppOutputData(),
    ]


class AppProcessOutputs(ExtendedSequenceSchema, AppNamespace):
    name = "ProcessOutputs"
    title = "ProcessOutputs"
    output = AppDataOutputItem()


class AppExecuteResponse(AppResponseBaseType, AppProcessVersion):
    name = "ExecuteResponse"
    title = "ExecuteResponse"  # not to be confused by 'Execute' used for request
    location = AppStatusLocationAttribute()
    svc_loc = AppServiceInstanceAttribute()
    process = AppProcessSummary()
    status = AppStatus()
    inputs = AppDataInputs(missing=drop)  # when lineage is requested only
    out_def = AppOutputDefinitions(missing=drop)  # when lineage is requested only
    outputs = AppProcessOutputs()


class AppXMLSuccessBodySchema(OneOfKeywordSchema):
    _one_of = [
        AppGetCapabilities(),
        AppDescribeProcess(),
        AppExecuteResponse(),
    ]


class AppExceptionCodeAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "exceptionCode"
    title = "Exception"
    attribute = True


class AppExceptionLocatorAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "locator"
    attribute = True


class AppExceptionText(ExtendedSchemaNode, AppNamespace):
    schema_type = String
    name = "ExceptionText"


class AppException(ExtendedMappingSchema, AppNamespace):
    name = "Exception"
    title = "Exception"
    code = AppExceptionCodeAttribute(example="MissingParameterValue")
    locator = AppExceptionLocatorAttribute(default="None", example="service")
    text = AppExceptionText(example="Missing service")


class AppExceptionReport(ExtendedMappingSchema, AppNamespace):
    name = "ExceptionReport"
    title = "ExceptionReport"
    exception = AppException()


class AppError(ExtendedMappingSchema):
    report = AppExceptionReport()


class OkAppResponse(ExtendedMappingSchema):
    description = "App operation successful"
    header = XmlHeader()
    body = AppXMLSuccessBodySchema()


class ErrorAppResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred on App endpoint."
    header = XmlHeader()
    body = AppError()


##################################################################################################################
# Path parameter definitions
#   These will document the path parameters of corresponding requests that uses them.
##################################################################################################################


class ProcessPath(ExtendedMappingSchema):
    process_id = AnyIdentifier(description="Process identifier (SLUG or UUID).", example="my-rrocess")


class JobPath(ExtendedMappingSchema):
    job_id = UUID(description="Job ID", example="14c68477-c3ed-4784-9c0f-a4c9e1344db5")


##################################################################################################################
# Request schemas
##################################################################################################################


class FrontpageEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class OpenAPIEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class SwaggerUIEndpoint(ExtendedMappingSchema):
    pass


class ProcessEndpoint(ProcessPath):
    header = RequestHeaders()


class JobEndpoint(JobPath):
    header = RequestHeaders()


class ProcessInputsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class JobInputsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessOutputsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class JobOutputsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessResultEndpoint(ProcessOutputsEndpoint):
    deprecated = True
    header = RequestHeaders()


class JobResultEndpoint(JobOutputsEndpoint):
    deprecated = True
    header = RequestHeaders()


class ProcessResultsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class JobExceptionsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessExceptionsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class JobLogsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessLogsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


##################################################################################################################
# Schema classes that define requests and response body content
##################################################################################################################


class CreateProviderRequestBody(ExtendedMappingSchema):
    id = AnyIdentifier()
    url = URL(description="Endpoint where to query the provider.")
    public = ExtendedSchemaNode(Boolean())


class InputDataType(InputIdentifierType):
    pass


class OutputDataType(OutputIdentifierType):
    format = Format(missing=drop)


class OutputList(ExtendedSequenceSchema):
    output = OutputDataType()


class ProviderSummarySchema(ExtendedMappingSchema):
    """App provider summary definition."""
    id = ExtendedSchemaNode(String())
    url = URL(description="Endpoint of the provider.")
    title = ExtendedSchemaNode(String())
    abstract = ExtendedSchemaNode(String())
    public = ExtendedSchemaNode(Boolean())


class ProviderCapabilitiesSchema(ExtendedMappingSchema):
    """App provider capabilities."""
    id = ExtendedSchemaNode(String())
    url = URL(description="App GetCapabilities URL of the provider.")
    title = ExtendedSchemaNode(String())
    abstract = ExtendedSchemaNode(String())
    contact = ExtendedSchemaNode(String())
    type = ExtendedSchemaNode(String())


class ExceptionReportType(ExtendedMappingSchema):
    code = ExtendedSchemaNode(String())
    description = ExtendedSchemaNode(String(), missing=drop)


class ProcessSummary(ProcessDescriptionType, ProcessDescriptionMeta):
    """App process definition."""
    processDescriptionURL = URL(description="Process description endpoint.",
                                missing=drop, title="processDescriptionURL")


class ProcessSummaryList(ExtendedSequenceSchema):
    processSummary = ProcessSummary()


class ProcessCollection(ExtendedMappingSchema):
    processes = ProcessSummaryList()


class ProcessInfo(ExtendedMappingSchema):
    executeEndpoint = URL(description="Endpoint where the process can be executed from.", missing=drop)


class Process(ProcessInfo, ProcessDescriptionType, ProcessDescriptionMeta):
    inputs = InputTypeList(description="Inputs definition of the process.")
    outputs = OutputDescriptionList(description="Outputs definition of the process.")


class ProcessOutputDescriptionSchema(ExtendedMappingSchema):
    """App process output definition."""
    dataType = ExtendedSchemaNode(String())
    defaultValue = ExtendedMappingSchema()
    id = ExtendedSchemaNode(String())
    abstract = ExtendedSchemaNode(String())
    title = ExtendedSchemaNode(String())


class JobStatusInfo(ExtendedMappingSchema):
    jobID = UUID(example="a9d14bf4-84e0-449a-bac8-16e598efe807", description="ID of the job.")
    status = JobStatusEnum(description="Last updated status.")
    message = ExtendedSchemaNode(String(), missing=drop, description="Information about the last status update.")
    created = ExtendedSchemaNode(DateTime(), missing=drop, default=None,
                                 description="Timestamp when the process execution job was created.")
    started = ExtendedSchemaNode(DateTime(), missing=drop, default=None,
                                 description="Timestamp when the process started execution if applicable.")
    finished = ExtendedSchemaNode(DateTime(), missing=drop, default=None,
                                  description="Timestamp when the process completed execution if applicable.")
    # note: using String instead of Time because timedelta object cannot be directly handled (missing parts at parsing)
    duration = ExtendedSchemaNode(String(), missing=drop,
                                  description="Duration since the start of the process execution.")
    runningSeconds = ExtendedSchemaNode(Integer(), missing=drop,
                                        description="Duration in seconds since the start of the process execution.")
    expirationDate = ExtendedSchemaNode(DateTime(), missing=drop,
                                        description="Timestamp when the job will be canceled if not yet completed.")
    estimatedCompletion = ExtendedSchemaNode(DateTime(), missing=drop)
    nextPoll = ExtendedSchemaNode(DateTime(), missing=drop,
                                  description="Timestamp when the job will prompted for updated status details.")
    percentCompleted = ExtendedSchemaNode(Integer(), example=0, validator=Range(min=0, max=100),
                                          description="Completion percentage of the job as indicated by the process.")
    links = LinkList(missing=drop)


class JobEntrySchema(OneOfKeywordSchema):
    # note:
    #   Since JobID is a simple string (not a dict), no additional mapping field can be added here.
    #   They will be discarded by `OneOfKeywordSchema.deserialize()`.
    _one_of = [
        JobStatusInfo,
        ExtendedSchemaNode(String(), description="Job ID."),
    ]


class JobCollection(ExtendedSequenceSchema):
    item = JobEntrySchema()


class CreatedJobStatusSchema(ExtendedMappingSchema):
    status = ExtendedSchemaNode(String(), example=JobStatuses.ACCEPTED.value)
    location = ExtendedSchemaNode(String(), example="http://{host}/weaver/processes/{my-process-id}/jobs/{my-job-id}")
    jobID = UUID(description="ID of the created job.")


class CreatedQuotedJobStatusSchema(CreatedJobStatusSchema):
    bill = UUID(description="ID of the created bill.")


class GetPagingJobsSchema(ExtendedMappingSchema):
    jobs = JobCollection()
    limit = ExtendedSchemaNode(Integer(), default=10)
    page = ExtendedSchemaNode(Integer(), validator=Range(min=0))


class JobCategoryFilters(PermissiveMappingSchema):
    category = ExtendedSchemaNode(String(), title="CategoryFilter", variable="<category>", default=None, missing=None,
                                  description="Value of the corresponding parameter forming that category group.")


class GroupedJobsCategorySchema(ExtendedMappingSchema):
    category = JobCategoryFilters(description="Grouping values that compose the corresponding job list category.")
    jobs = JobCollection(description="List of jobs that matched the corresponding grouping values.")
    count = ExtendedSchemaNode(Integer(), description="Number of matching jobs for the corresponding group category.")


class GroupedCategoryJobsSchema(ExtendedSequenceSchema):
    job_group_category_item = GroupedJobsCategorySchema()


class GetGroupedJobsSchema(ExtendedMappingSchema):
    groups = GroupedCategoryJobsSchema()


class GetQueriedJobsSchema(OneOfKeywordSchema):
    _one_of = [
        GetPagingJobsSchema,
        GetGroupedJobsSchema,
    ]
    total = ExtendedSchemaNode(Integer(),
                               description="Total number of matched jobs regardless of grouping or paging result.")


class DismissedJobSchema(ExtendedMappingSchema):
    status = JobStatusEnum()
    jobID = UUID(description="ID of the job.")
    message = ExtendedSchemaNode(String(), example="Job dismissed.")
    percentCompleted = ExtendedSchemaNode(Integer(), example=0)


class QuoteProcessParametersSchema(ExtendedMappingSchema):
    inputs = InputTypeList(missing=drop)
    outputs = OutputDescriptionList(missing=drop)


class Reference(ExtendedMappingSchema):
    title = "Reference"
    href = ReferenceURL(description="Endpoint of the reference.")
    format = Format(missing=drop)
    body = ExtendedSchemaNode(String(), missing=drop)
    bodyReference = ReferenceURL(missing=drop)


class AnyType(OneOfKeywordSchema):
    """Permissive variants that we attempt to parse automatically."""
    _one_of = [
        # literal data with 'data' key (object as {"data": <the-value>})
        AnyLiteralDataType(),
        # same with 'value' key (object as {"value": <the-value>})
        AnyLiteralValueType(),
        # HTTP references key (object as {"reference": <some-URL>})
        LiteralReference(),
        # HTTP references detail (object as {"href": <some-URL>, "format": {format-obj}, ...})
        Reference(),
    ]


class Input(InputDataType, AnyType):
    """
    Default value to be looked for uses key 'value' to conform to OGC API standard.
    We still look for 'href', 'data' and 'reference' to remain back-compatible.
    """


class InputList(ExtendedSequenceSchema):
    input = Input(missing=drop, description="Received input definition during job submission.")


class Execute(ExtendedMappingSchema):
    inputs = InputList()
    outputs = OutputList()
    notification_email = ExtendedSchemaNode(
        String(),
        missing=drop,
        validator=Email(),
        description="Optionally send a notification email when the job is done.")


class SupportedValues(ExtendedMappingSchema):
    pass


class DefaultValues(ExtendedMappingSchema):
    pass


class ProcessInputDefaultValues(ExtendedSequenceSchema):
    value = DefaultValues()


class ProcessInputSupportedValues(ExtendedSequenceSchema):
    value = SupportedValues()


class ProcessInputDescriptionSchema(ExtendedMappingSchema):
    id = AnyIdentifier()
    title = ExtendedSchemaNode(String())
    dataType = ExtendedSchemaNode(String())
    abstract = ExtendedSchemaNode(String())
    minOccurs = MinOccursDefinition()
    maxOccurs = MaxOccursDefinition()
    defaultValue = ProcessInputDefaultValues()
    supportedValues = ProcessInputSupportedValues()


class ProcessInputDescriptionList(ExtendedSequenceSchema):
    input = ProcessInputDescriptionSchema()


class ProcessOutputDescriptionList(ExtendedSequenceSchema):
    input = ProcessOutputDescriptionSchema()


class ProcessDescriptionSchema(ExtendedMappingSchema):
    id = AnyIdentifier()
    label = ExtendedSchemaNode(String())
    description = ExtendedSchemaNode(String())
    inputs = ProcessInputDescriptionList()
    outputs = ProcessOutputDescriptionList()


class UndeploymentResult(ExtendedMappingSchema):
    id = AnyIdentifier()


class DeploymentResult(ExtendedMappingSchema):
    processSummary = ProcessSummary()


class ProcessDescriptionBodySchema(ExtendedMappingSchema):
    process = ProcessDescriptionSchema()


class ProvidersSchema(ExtendedSequenceSchema):
    providers_service = ProviderSummarySchema()


class ProcessesSchema(ExtendedSequenceSchema):
    provider_processes_service = ProcessInputDescriptionSchema()


class JobOutputValue(OneOfKeywordSchema):
    _one_of = [
        Reference(tilte="JobOutputReference"),
        AnyLiteralDataType(title="JobOutputLiteral")
    ]


class JobOutput(AllOfKeywordSchema):
    _all_of = [
        OutputDataType(),
        JobOutputValue(),
    ]


class JobOutputList(ExtendedSequenceSchema):
    title = "JobOutputList"
    output = JobOutput(description="Job output result with specific keyword according to represented format.")


class ResultLiteral(AnyLiteralValueType, LiteralDataDomainDefinition):
    # value = <AnyLiteralValueType>
    pass


class ResultLiteralList(ExtendedSequenceSchema):
    result = ResultLiteral()


class ValueFormatted(ExtendedMappingSchema):
    value = ExtendedSchemaNode(
        String(),
        example="<xml><data>test</data></xml>",
        description="Formatted content value of the result."
    )
    format = FormatMedia()


class ValueFormattedList(ExtendedSequenceSchema):
    result = ValueFormatted()


class ResultReference(ExtendedMappingSchema):
    href = ReferenceURL(description="Result file reference.")
    format = FormatMedia()


class ResultReferenceList(ExtendedSequenceSchema):
    result = ResultReference()


class ResultData(OneOfKeywordSchema):
    _one_of = [
        # must place formatted value first since both value/format fields are simultaneously required
        # other classes require only one of the two, and therefore are more permissive during schema validation
        ValueFormatted(description="Result formatted content value."),
        ValueFormattedList(description="Result formatted content of multiple values."),
        ResultReference(description="Result reference location."),
        ResultReferenceList(description="Result locations for multiple references."),
        ResultLiteral(description="Result literal value."),
        ResultLiteralList(description="Result list of literal values."),
    ]


class Result(ExtendedMappingSchema):
    """Result outputs obtained from a successful process job execution."""
    output_id = ResultData(
        variable="<output-id>", title="Output Identifier",
        description=(
            "Resulting value of the output that conforms to 'OGC-API - Processes' standard. "
            "(Note: '<output-id>' is a variable corresponding for each output identifier of the process)"
        )
    )


class JobInputsSchema(ExtendedMappingSchema):
    inputs = InputList()
    links = LinkList(missing=drop)


class JobOutputsSchema(ExtendedMappingSchema):
    outputs = JobOutputList()
    links = LinkList(missing=drop)


class JobException(ExtendedMappingSchema):
    # note: test fields correspond exactly to 'Applib.App.AppException', they are deserialized as is
    Code = ExtendedSchemaNode(String())
    Locator = ExtendedSchemaNode(String(), default=None)
    Text = ExtendedSchemaNode(String())


class JobExceptionsSchema(ExtendedSequenceSchema):
    exceptions = JobException()


class JobLogsSchema(ExtendedSequenceSchema):
    log = ExtendedSchemaNode(String())


class FrontpageParameterSchema(ExtendedMappingSchema):
    name = ExtendedSchemaNode(String(), example="api")
    enabled = ExtendedSchemaNode(Boolean(), example=True)
    url = URL(description="Referenced parameter endpoint.", example="https://demo-api", missing=drop)
    doc = ExtendedSchemaNode(String(), example="https://demo-api/api", missing=drop)


class FrontpageParameters(ExtendedSequenceSchema):
    parameter = FrontpageParameterSchema()


class FrontpageSchema(ExtendedMappingSchema):
    message = ExtendedSchemaNode(String(), default="Demo API Information", example="API Information")
    description = ExtendedSchemaNode(String(), default="default", example="default")
    parameters = FrontpageParameters()


class SwaggerJSONSpecSchema(ExtendedMappingSchema):
    pass


class SwaggerUISpecSchema(ExtendedMappingSchema):
    pass


class VersionsSpecSchema(ExtendedMappingSchema):
    name = ExtendedSchemaNode(String(), description="Identification name of the current item.", example="weaver")
    type = ExtendedSchemaNode(String(), description="Identification type of the current item.", example="api")
    version = Version(description="Version of the current item.", example="0.1.0")


class VersionsList(ExtendedSequenceSchema):
    version = VersionsSpecSchema()


class VersionsSchema(ExtendedMappingSchema):
    versions = VersionsList()


class ConformanceList(ExtendedSequenceSchema):
    conformance = URL(description="Conformance specification link.",
                      example="http://www.opengis.net/spec/App/2.0/req/service/binding/rest-json/core")


class ConformanceSchema(ExtendedMappingSchema):
    conformsTo = ConformanceList()


class Deploy(ExtendedMappingSchema):
    name = ExtendedSchemaNode(String())
    version = Version(missing=drop)
    id = AnyIdentifier()


class PostProcessesEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()
    body = Deploy(title="Deploy")


class GetJobsQueries(ExtendedMappingSchema):
    detail = ExtendedSchemaNode(Boolean(), description="Provide job details instead of IDs.",
                                default=False, example=True, missing=drop)
    groups = ExtendedSchemaNode(String(),
                                description="Comma-separated list of grouping fields with which to list jobs.",
                                default=False, example="process,service", missing=drop)
    page = ExtendedSchemaNode(Integer(), missing=drop, default=0, validator=Range(min=0))
    limit = ExtendedSchemaNode(Integer(), missing=drop, default=10)
    status = JobStatusEnum(missing=drop)
    process = ProcessIdentifier(missing=None)
    provider = ExtendedSchemaNode(String(), missing=drop, default=None)
    sort = JobSortEnum(missing=drop)
    tags = ExtendedSchemaNode(String(), missing=drop, default=None,
                              description="Comma-separated values of tags assigned to jobs")


class GetJobsRequest(ExtendedMappingSchema):
    header = RequestHeaders()
    querystring = GetJobsQueries()


class GetJobsEndpoint(GetJobsRequest):
    pass


class GetProcessJobsEndpoint(GetJobsRequest, ProcessPath):
    pass


class GetProcessJobEndpoint(ProcessPath):
    header = RequestHeaders()


class DeleteProcessJobEndpoint(ProcessPath):
    header = RequestHeaders()


##################################################################################################################
# Responses schemas
##################################################################################################################

class ErrorDetail(ExtendedMappingSchema):
    code = ExtendedSchemaNode(Integer(), description="HTTP status code.", example=400)
    status = ExtendedSchemaNode(String(), description="HTTP status detail.", example="400 Bad Request")


class AppErrorCode(ExtendedSchemaNode):
    schema_type = String
    example = "InvalidParameterValue"
    description = "App error code."


class AppExceptionResponse(ExtendedMappingSchema):
    """Error content in XML format"""
    description = "App formatted exception."
    code = AppErrorCode(example="NoSuchProcess")
    locator = ExtendedSchemaNode(String(), example="identifier",
                                 description="Indication of the element that caused the error.")
    message = ExtendedSchemaNode(String(), example="Invalid process ID.",
                                 description="Specific description of the error.")


class ErrorJsonResponseBodySchema(ExtendedMappingSchema):
    code = AppErrorCode()
    description = ExtendedSchemaNode(String(), description="Detail about the cause of error.")
    error = ErrorDetail(missing=drop)
    exception = AppExceptionResponse(missing=drop)


class ForbiddenProcessAccessResponseSchema(ExtendedMappingSchema):
    description = "Referenced process is not accessible."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class InternalServerErrorResponseSchema(ExtendedMappingSchema):
    description = "Unhandled internal server error."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class OkGetFrontpageResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = FrontpageSchema()


class OkGetSwaggerJSONResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = SwaggerJSONSpecSchema(description="OpenAPI JSON schema of Weaver API.")


class OkGetSwaggerUIResponse(ExtendedMappingSchema):
    header = HtmlHeader()
    body = SwaggerUISpecSchema(description="Swagger UI of Weaver API.")


class OkGetRedocUIResponse(ExtendedMappingSchema):
    header = HtmlHeader()
    body = SwaggerUISpecSchema(description="Redoc UI of Weaver API.")


class OkGetVersionsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = VersionsSchema()


class OkGetConformanceResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ConformanceSchema()


class OkGetProvidersListResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProvidersSchema()


class OkGetProviderCapabilitiesSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProviderCapabilitiesSchema()


class NoContentDeleteProviderSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = NoContent()


class NotImplementedDeleteProviderResponse(ExtendedMappingSchema):
    description = "Provider removal not supported using referenced storage."


class OkGetProviderProcessesSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessesSchema()


class GetProcessesQuery(ExtendedMappingSchema):
    detail = ExtendedSchemaNode(
        Boolean(), example=True, default=True, missing=drop,
        description="Return summary details about each process, or simply their IDs."
    )


class GetProcessesEndpoint(ExtendedMappingSchema):
    querystring = GetProcessesQuery()


class OkGetProcessesListResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessCollection()


class ProcessDeployBodySchema(ExtendedMappingSchema):
    deploymentDone = ExtendedSchemaNode(Boolean(), default=False, example=True,
                                        description="Indicates if the process was successfully deployed.")
    processSummary = ProcessSummary(missing=drop, description="Deployed process summary if successful.")
    failureReason = ExtendedSchemaNode(String(), missing=drop,
                                       description="Description of deploy failure if applicable.")


class CreatedProcessesResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessDeployBodySchema()


class OkDeleteProcessUndeployBodySchema(ExtendedMappingSchema):
    deploymentDone = ExtendedSchemaNode(Boolean(), default=False, example=True,
                                        description="Indicates if the process was successfully undeployed.")
    identifier = ExtendedSchemaNode(String(), example="workflow")
    failureReason = ExtendedSchemaNode(String(), missing=drop,
                                       description="Description of undeploy failure if applicable.")


class OkDeleteProcessResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = OkDeleteProcessUndeployBodySchema()


class BadRequestGetProcessInfoResponse(ExtendedMappingSchema):
    description = "Missing process identifier."
    body = NoContent()


class OkGetProcessResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = Process()


class CreatedAcceptJobResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = CreatedJobStatusSchema()


class OkGetProcessJobResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobStatusInfo()


class OkDeleteProcessJobResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = DismissedJobSchema()


class OkGetQueriedJobsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = GetQueriedJobsSchema()


class OkDismissJobResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = DismissedJobSchema()


class OkGetJobStatusResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobStatusInfo()


class NotFoundJobResponseSchema(ExtendedMappingSchema):
    description = "Job reference UUID cannot be found."
    examples = {
        # examples of output that will be rendered in the Swagger UI
        # this is one way to define them, they can also be specified in the responses themselves (see farther below)
        "JobNotFound": {
            "summary": "Example response when specified job reference cannot be found.",
            "value": {
                "id": "11111111-2222-3333-4444-555555555555",
                "msg": "job does not exist"
            }
        }
    }
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class OkGetJobInputsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobInputsSchema()


class OkGetJobOutputsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobOutputsSchema()


class RedirectResultResponse(ExtendedMappingSchema):
    header = RedirectHeaders()


class OkGetJobResultsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = Result()

class OkGetJobExceptionsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobExceptionsSchema()


class OkGetJobLogsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobLogsSchema()


get_api_frontpage_responses = {
    "200": OkGetFrontpageResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_openapi_json_responses = {
    "200": OkGetSwaggerJSONResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_api_swagger_ui_responses = {
    "200": OkGetSwaggerUIResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_api_redoc_ui_responses = {
    "200": OkGetRedocUIResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_api_versions_responses = {
    "200": OkGetVersionsResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_api_conformance_responses = {
    "200": OkGetConformanceResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_processes_responses = {
    "200": OkGetProcessesListResponse(description="success", examples={
        "ProcessesList": {
            "summary": "Listing of registered processes.",
            "value": EXAMPLES["process_listing.json"]["data"],
        }
    }),
    "500": InternalServerErrorResponseSchema(),
}
post_processes_responses = {
    "201": CreatedProcessesResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_process_responses = {
    "200": OkGetProcessResponse(
        description="success",
        # detailed response examples from external file content!
        examples={
            "ProcessDescription": {
                "summary": "Description of a process.",
                # file path must be found relative to where the API schema gets generated and published
                # otherwise, provide an absolute path to make sure it gets found
                # here we use examples that where pre-loaded earlier for convenience
                # NOTE: 'path' is used, so 'externalValue' is defined instead of directly providing 'value'
                "externalValue": EXAMPLES["process_description.json"]["path"],
            }
        }
    ),
    "400": BadRequestGetProcessInfoResponse(),
    "500": InternalServerErrorResponseSchema(),
}
delete_process_responses = {
    "200": OkDeleteProcessResponse(description="success"),
    "403": ForbiddenProcessAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_jobs_responses = {
    "200": OkGetQueriedJobsResponse(
        description="success",
        # detailed response examples from literal content!
        examples={
            "JobListing": {
                "summary": "Job ID listing with default queries.",
                "value": {
                    "jobs": [
                        "a9d14bf4-84e0-449a-bac8-16e598efe807",
                        "84e0a9f5-498a-2345-1244-afe54a234cb1"
                    ]
                }
            }
        }
    ),
    "500": InternalServerErrorResponseSchema(),
}
get_job_responses = {
    "200": OkGetJobStatusResponse(
        description="success",
        examples={
            # any number of examples is supported for responses!
            "JobStatusSuccess": {
                "summary": "Successful job status response.",
                "value": EXAMPLES["job_status_success.json"]},
            "JobStatusFailure": {
                "summary": "Failed job status response.",
                "value": EXAMPLES["job_status_failed.json"],
            }
        }
    ),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
delete_job_responses = {
    "200": OkDismissJobResponse(description="success"),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
xml_app_responses = {
    "200": OkAppResponse(examples={
        "GetCapabilities": {
            "summary": "GetCapabilities example response.",
            "value": EXAMPLES["wps_getcapabilities.xml"]
        },
        "DescribeProcess": {
            "summary": "DescribeProcess example response.",
            "value": EXAMPLES["wps_describeprocess.xml"]
        },
        # "Execute": # no implemented for demo
    }),
    "400": ErrorAppResponse(examples={
        "MissingParameterError": {
            "summary": "Error report in case of missing request parameter.",
            "value": EXAMPLES["wps_missing_parameter.xml"],
        }
    }),
    "500": ErrorAppResponse(),
}


##################################
# Define some test data, only for demonstration purposes
#
# In a real application, these would probably be retrieved from a database or some file system structure.


_PROCESSES = {
    "example": {
        "name": "example",
        "1d": "11111111-2222-3333-4444-555555555555",
        "version": "1.2.3",
        "created": "2021-04-30T01:28:57"
    }
}
_JOBS = [
    "a9d14bf4-84e0-449a-bac8-16e598efe807",
    "84e0a9f5-498a-2345-1244-afe54a234cb1"
]


##################################

class DemoProcessJobAPI(object):
    """
    The Web Application that will use the OpenAPI schema objects defined above.
    """

    @staticmethod
    @api_frontpage_service.get(tags=[TAG_API], response_schemas=get_api_frontpage_responses)
    def get_api(request):
        url = request.url[:-1] if request.url.endswith("/") else request.url
        data = {
            "message": "Demo API",
            "description": "This is a demo app to demonstrate support of OpenAPI v3 schema generation.",
            "parameters": [
                {"name": "schema", "url": url + openapi_json_service.path, "enabled": True},
                {"name": "swagger", "url": url + api_openapi_ui_service.path, "enabled": True},
                {"name": "processes", "url": url + processes_service.path, "enabled": True},
                {"name": "jobs", "url": url + jobs_service.path, "enabled": True},
                {"name": "xml", "url": url + xml_service.path, "enabled": True},
            ]
        }
        return HTTPOk(json=data)

    @staticmethod
    @processes_service.get(tags=[TAG_PROCESSES], response_schemas=get_processes_responses)
    def get_processes(request):
        """Get the list of processes."""
        detail = request.params("detail", False)
        if detail:
            return _PROCESSES
        return [proc["name"] for proc in _PROCESSES]

    @staticmethod
    @processes_service.post(tags=[TAG_PROCESSES], schema=Deploy(), response_schemas=post_processes_responses)
    def create_processes(request):
        """Create a new process."""
        body = {}
        if "name" not in body:
            raise HTTPBadRequest("missing the name!")
        if "name" in _PROCESSES:
            raise HTTPConflict("process name already exist")
        body["created"] = datetime.datetime.now().isoformat().split(".")[0]
        _PROCESSES[body["name"]] = body
        return HTTPCreated("process deployed")

    @staticmethod
    @process_service.get(tags=[TAG_PROCESSES], response_schemas=get_process_responses)
    def get_process(request):
        """Get a single process."""
        process = request.matchdict['process_id']
        if process not in _PROCESSES:
            raise HTTPNotFound("process not found")
        return HTTPOk(json=_PROCESSES[process])

    @staticmethod
    @job_service.get(tags=[TAG_JOBS], response_schemas=get_job_responses)
    def get_job(request):
        """Retrieve some job by UUID."""
        job_id = request.matchdict("job_id")
        if not job_id:
            raise HTTPBadRequest("invalid job id")
        if job_id not in _JOBS:
            raise HTTPNotFound(json=EXAMPLES["job_not_found.json"]["data"])  # reuse for convenience
        return HTTPOk(json=_JOBS[job_id])

    @staticmethod
    @xml_service.get(tags=[TAG_PROCESSES], response_schemas=xml_app_responses)
    def app_xml_endpoint(request):
        """XML endpoint of the application."""

        # here we will use the predefined XML examples for convenience
        # a real application would have to implement adequate processing and functionality
        req = str(request.params.get("request", "")).lower()
        err = EXAMPLES["wps_missing_parameter.xml"]["data"]
        if req == "execute":
            return HTTPNotImplemented(detail="Not implemented for this demo.")
        if req not in ["getcapabilities", "describeprocess"]:
            return HTTPBadRequest(detail="Missing parameter", body=err)
        if req == "getcapabilities":
            return HTTPOk(body=EXAMPLES["wps_getcapabilities.xml"])
        proc = str(request.params.get("process", ""))
        if proc != "demo":
            err = err.replace("Missing", "Invalid").replace("request", "process")
            return HTTPBadRequest(detail="Invalid parameter", body=err)
        return HTTPOk(body=EXAMPLES["app_describeprocess.xml"])
        

def make_app():
    config = Configurator()
    config.include("cornice")
    config.include("cornice_swagger")
    # Create views to serve our OpenAPI spec
    config.cornice_enable_openapi_view(
        api_path=openapi_json_service.path,
        title="DemoProcessJobAPI",
        description="OpenAPI documentation",
        version="1.0.0"
    )
    # Create views to serve OpenAPI spec UI explorer
    config.cornice_enable_openapi_explorer(api_explorer_path=api_openapi_ui_service.path)
    config.scan()
    app = config.make_wsgi_app()
    return app


def main():
    parser = argparse.ArgumentParser(description="Demo OpenAPI v3 application.", add_help=True)
    parser.add_argument("--host", "-H", help="Host where to run the app", default="localhost")
    parser.add_argument("--port", "-P", help="Port where to access the app", default=8001, type=int)
    args = parser.parse_args()
    app = make_app()
    url = "http://{}:{}".format(args.host, args.port)
    server = make_server(args.host, args.port, app)
    print("Visit me on {}".format(url))
    print("API explorer here: {}{}".format(url, api_openapi_ui_service.path))
    print("And the generated API schema here: {}{}".format(url, openapi_json_service.path))
    server.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
