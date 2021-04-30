"""
This module should contain any and every definitions in use to build the swagger UI,
so that one can update the swagger without touching any other files after the initial integration
"""
# pylint: disable=C0103,invalid-name

import datetime
import enum
import os
import yaml

from colander import DateTime, Email, OneOf, Range, drop, null, required
from cornice import Service
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPBadRequest, HTTPCreated, HTTPConflict, HTTPNotFound
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
    OneOfCaseInsensitive,  # ignore case for matching a string
    SemanticVersion,  # <major>.<minor>.<patch> strings
    StringRange,  # just like range, but can use numerical strings
)



#########################################################
# Examples
#########################################################

# load examples by file names as keys
SCHEMA_EXAMPLE_DIR = os.path.join(os.path.dirname(__file__), "examples")
EXAMPLES = {}
for name in os.listdir(SCHEMA_EXAMPLE_DIR):
    path = os.path.join(SCHEMA_EXAMPLE_DIR, name)
    ext = os.path.splitext(name)[-1]
    with open(path, "r") as f:
        if ext in [".json", ".yaml", ".yml"]:
            EXAMPLES[name] = yaml.safe_load(f)  # both JSON/YAML
        else:
            EXAMPLES[name] = f.read()


#########################################################
# API tags and metadata
#########################################################

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

###############################################################################
# API endpoints
# These "services" are wrappers that allow Cornice to generate the JSON API
###############################################################################

api_frontpage_service = Service(name="api_frontpage", path="/")
api_openapi_ui_service = Service(name="api_openapi_ui", path="/api")
openapi_json_service = Service(name="openapi_json", path="/json")

jobs_service = Service(name="jobs", path="/jobs")
job_service = Service(name="job", path=jobs_service.path + "/{job_id}")

processes_service = Service(name="processes", path="/processes")
process_service = Service(name="process", path=processes_service.path + "/{process_id}")


######################################################
# Repetitive constants

######################################################

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


class Sorting(enum.Enum):
    ASCENDING = "asc"
    DESCENDING = "desc"


#########################################################
# Generic schemas
#########################################################


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


class AcceptHeader(ExtendedSchemaNode):
    # ok to use 'name' in this case because target 'key' in the mapping must
    # be that specific value but cannot have a field named with this format
    name = "Accept"
    schema_type = String
    validator = OneOf(ContentType)
    missing = drop
    default = ContentType.APP_JSON.value  # defaults to JSON for easy use within browsers


class AcceptLanguageHeader(ExtendedSchemaNode):
    # ok to use 'name' in this case because target 'key' in the mapping must
    # be that specific value but cannot have a field named with this format
    name = "Accept-Language"
    schema_type = String
    missing = drop
    default = AcceptLanguage.EN_CA.value
    validator = OneOf(AcceptLanguage)


class JsonHeader(ExtendedMappingSchema):
    content_type = ContentTypeHeader(example=ContentType.APP_XML.value, default=ContentType.APP_XML.value)


class HtmlHeader(ExtendedMappingSchema):
    content_type = ContentTypeHeader(example=ContentType.TEXT_HTML.value, default=ContentType.TEXT_HTML.value)


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
    mimeType = ExtendedSchemaNode(String(), default=ContentType.TEXT_PLAIN, example=ContentType.APP_XML.value)


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
    """Format employed for reference results respecting 'OGC-API - Processes' schemas."""
    schema_ref = "{}/master/core/openapi/schemas/formatDescription.yaml".format(OGC_API_SCHEMA_URL)
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
    href = ReferenceURL(description="URL to CWL file.", title="OWSContentURL",
                        default=drop,       # if invalid, drop it completely,
                        missing=required,   # but still mark as 'required' for parent objects
                        example="http://some.host/applications/cwl/multisensor_ndvi.cwl")


class Offering(ExtendedMappingSchema):
    code = ExtendedSchemaNode(String(), missing=drop, description="Descriptor of represented information in 'content'.")
    content = Content()


class OWSContext(ExtendedMappingSchema):
    description = "OGC Web Service definition from an URL reference."
    title = "owsContext"
    offering = Offering()


class DescriptionBase(ExtendedMappingSchema):
    title = ExtendedSchemaNode(String(), missing=drop, description="Short name definition of the process.")
    abstract = ExtendedSchemaNode(String(), missing=drop, description="Detailed explanation of the process operation.")
    links = LinkList(missing=drop, description="References to endpoints with information related to the process.")


class DescriptionOWS(ExtendedMappingSchema):
    owsContext = OWSContext(missing=drop)


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
        missing=drop, default=[],
        description="Keywords applied to the process for search and categorization purposes.")
    metadata = MetadataList(
        missing=drop, default=[],
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


class ProcessDescriptionType(DescriptionType, DescriptionOWS):
    id = ProcessIdentifier()


class InputIdentifierType(ExtendedMappingSchema):
    id = AnyIdentifier(description=IO_INFO_IDS.format(first="WPS", second="CWL", what="input"))


class OutputIdentifierType(ExtendedMappingSchema):
    id = AnyIdentifier(description=IO_INFO_IDS.format(first="WPS", second="CWL", what="output"))


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
    schema_ref = "{}/master/core/openapi/schemas/nameReferenceType.yaml".format(OGC_API_SCHEMA_URL)
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


class JobSortEnum(ExtendedSchemaNode):
    schema_type = String
    title = "JobSortingMethod"
    default = Sorting.ASCENDING.value
    example = Sorting.ASCENDING.value
    validator = OneOf(Sorting)


#########################################################
# Path parameter definitions
#########################################################


class ProcessPath(ExtendedMappingSchema):
    process_id = AnyIdentifier(description="Process identifier (SLUG or UUID).", example="my-rrocess")


class JobPath(ExtendedMappingSchema):
    job_id = UUID(description="Job ID", example="14c68477-c3ed-4784-9c0f-a4c9e1344db5")


#########################################################
# These classes define each of the endpoints parameters
#########################################################


class FrontpageEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class OpenAPIEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class SwaggerUIEndpoint(ExtendedMappingSchema):
    pass


class XMLNamespace(XMLObject):
    prefix = "xml"


class AppNamespace(XMLObject):
    """Custom namespace for demo app."""
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


class OWSAcceptVersions(ExtendedSequenceSchema, OWSNamespace):
    description = "Accepted versions to produce the response."
    name = "AcceptVersions"
    item = AppVersion()


class OWSLanguage(ExtendedSchemaNode, OWSNamespace):
    description = "Desired language to produce the response."
    schema_type = String
    name = "Language"
    default = AcceptLanguage.EN_US.value
    example = AcceptLanguage.EN_CA.value


class OWSLanguageAttribute(OWSLanguage):
    description = "RFC-4646 language code of the human-readable text."
    name = "language"
    attribute = True


class OWSService(ExtendedSchemaNode, OWSNamespace):
    description = "Desired service to produce the response (SHOULD be 'WPS')."
    schema_type = String
    name = "service"
    attribute = True
    default = AcceptLanguage.EN_US.value
    example = AcceptLanguage.EN_CA.value


class WPSServiceAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "service"
    attribute = True
    default = "WPS"
    example = "WPS"


class WPSVersionAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "version"
    attribute = True
    default = "1.0.0"
    example = "1.0.0"


class WPSLanguageAttribute(ExtendedSchemaNode, XMLNamespace):
    schema_type = String
    name = "lang"
    attribute = True
    default = AcceptLanguage.EN_US.value
    example = AcceptLanguage.EN_CA.value


class WPSParameters(ExtendedMappingSchema):
    service = ExtendedSchemaNode(String(), example="WPS", description="Service selection.",
                                 validator=OneOfCaseInsensitive(["WPS"]))
    request = ExtendedSchemaNode(String(), example="GetCapabilities", description="WPS operation to accomplish",
                                 validator=OneOfCaseInsensitive(["GetCapabilities", "DescribeProcess", "Execute"]))
    version = Version(exaple="1.0.0", default="1.0.0", validator=OneOf(["1.0.0", "2.0.0", "2.0"]))
    identifier = ExtendedSchemaNode(String(), exaple="hello", missing=drop,
                                    example="example-process,another-process",
                                    description="Single or comma-separated list of process identifiers to describe, "
                                                "and single one for execution.")
    data_inputs = ExtendedSchemaNode(String(), name="DataInputs", missing=drop,
                                     example="message=hi&names=user1,user2&value=1",
                                     description="Process execution inputs provided as Key-Value Pairs (KVP).")


class WPSOperationGetNoContent(ExtendedMappingSchema):
    description = "No content body provided (GET requests)."
    default = {}


class WPSOperationPost(ExtendedMappingSchema):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/common/RequestBaseType.xsd"
    accepted_versions = OWSAcceptVersions(missing=drop, default="1.0.0")
    language = OWSLanguageAttribute(missing=drop)
    service = OWSService()


class WPSGetCapabilitiesPost(WPSOperationPost, WPSNamespace):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsGetCapabilities_request.xsd"
    name = "GetCapabilities"
    title = "GetCapabilities"


class OWSIdentifier(ExtendedSchemaNode, OWSNamespace):
    schema_type = String
    name = "Identifier"


class OWSIdentifierList(ExtendedSequenceSchema, OWSNamespace):
    name = "Identifiers"
    item = OWSIdentifier()


class OWSTitle(ExtendedSchemaNode, OWSNamespace):
    schema_type = String
    name = "Title"


class OWSAbstract(ExtendedSchemaNode, OWSNamespace):
    schema_type = String
    name = "Abstract"


class OWSMetadataLink(ExtendedSchemaNode, XMLObject):
    schema_name = "Metadata"
    schema_type = String
    attribute = True
    name = "Metadata"
    prefix = "xlink"
    example = "WPS"
    wrapped = False  # metadata xlink at same level as other items


class OWSMetadata(ExtendedSequenceSchema, OWSNamespace):
    schema_type = String
    name = "Metadata"
    title = OWSMetadataLink(missing=drop)


class WPSDescribeProcessPost(WPSOperationPost, WPSNamespace):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsDescribeProcess_request.xsd"
    name = "DescribeProcess"
    title = "DescribeProcess"
    identifier = OWSIdentifierList(
        description="Single or comma-separated list of process identifier to describe.",
        example="example"
    )


class WPSExecuteDataInputs(ExtendedMappingSchema, WPSNamespace):
    description = "XML data inputs provided for WPS POST request (Execute)."
    name = "DataInputs"
    title = "DataInputs"
    # FIXME: missing details about 'DataInputs'


class WPSExecutePost(WPSOperationPost, WPSNamespace):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsExecute_request.xsd"
    name = "Execute"
    title = "Execute"
    identifier = OWSIdentifier(description="Identifier of the process to execute with data inputs.")
    dataInputs = WPSExecuteDataInputs(description="Data inputs to be provided for process execution.")


class WPSRequestBody(OneOfKeywordSchema):
    _one_of = [
        WPSExecutePost(),
        WPSDescribeProcessPost(),
        WPSGetCapabilitiesPost(),
    ]
    examples = {
        "Execute": {
            "summary": "Execute request example.",
            "value": EXAMPLES["wps_execute_request.xml"]
        }
    }


class WPSHeaders(ExtendedMappingSchema):
    accept = AcceptHeader(missing=drop)


class WPSEndpointGet(ExtendedMappingSchema):
    header = WPSHeaders()
    querystring = WPSParameters()
    body = WPSOperationGetNoContent(missing=drop)


class WPSEndpointPost(ExtendedMappingSchema):
    header = WPSHeaders()
    body = WPSRequestBody()


class XMLBooleanAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = Boolean
    attribute = True


class XMLString(ExtendedSchemaNode, XMLObject):
    schema_type = String


class OWSString(ExtendedSchemaNode, OWSNamespace):
    schema_type = String


class OWSKeywordList(ExtendedSequenceSchema, OWSNamespace):
    title = "OWSKeywords"
    keyword = OWSString(name="Keyword", title="OWSKeyword", example="Weaver")


class OWSType(ExtendedMappingSchema, OWSNamespace):
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


class OWSPhone(ExtendedMappingSchema, OWSNamespace):
    name = "Phone"
    voice = OWSString(name="Voice", title="OWSVoice", example="1-234-567-8910", missing=drop)
    facsimile = OWSString(name="Facsimile", title="OWSFacsimile", missing=drop)


class OWSAddress(ExtendedMappingSchema, OWSNamespace):
    name = "Address"
    delivery_point = OWSString(name="DeliveryPoint", title="OWSDeliveryPoint",
                               example="123 Place Street", missing=drop)
    city = OWSString(name="City", title="OWSCity", example="Nowhere", missing=drop)
    country = OWSString(name="Country", title="OWSCountry", missing=drop)
    admin_area = OWSString(name="AdministrativeArea", title="AdministrativeArea", missing=drop)
    postal_code = OWSString(name="PostalCode", title="OWSPostalCode", example="A1B 2C3", missing=drop)
    email = OWSString(name="ElectronicMailAddress", title="OWSElectronicMailAddress",
                      example="mail@me.com", validator=Email, missing=drop)


class OWSContactInfo(ExtendedMappingSchema, OWSNamespace):
    name = "ContactInfo"
    phone = OWSPhone(missing=drop)
    address = OWSAddress(missing=drop)


class OWSServiceContact(ExtendedMappingSchema, OWSNamespace):
    name = "ServiceContact"
    individual = OWSString(name="IndividualName", title="OWSIndividualName", example="John Smith", missing=drop)
    position = OWSString(name="PositionName", title="OWSPositionName", example="One Man Team", missing=drop)
    contact = OWSContactInfo(missing=drop, default={})


class OWSServiceProvider(ExtendedMappingSchema, OWSNamespace):
    description = "Details about the institution providing the service."
    name = "ServiceProvider"
    title = "ServiceProvider"
    provider_name = OWSString(name="ProviderName", title="OWSProviderName", example="EXAMPLE")
    provider_site = OWSString(name="ProviderName", title="OWSProviderName", example="http://schema-example.com")
    contact = OWSServiceContact(required=False, defalult={})


class WPSDescriptionType(ExtendedMappingSchema, OWSNamespace):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/common/DescriptionType.xsd"
    name = "DescriptionType"
    _title = OWSTitle(description="Title of the service.", example="Weaver")
    abstract = OWSAbstract(description="Detail about the service.", example="Weaver WPS example schema.", missing=drop)
    metadata = OWSMetadata(description="Metadata of the service.", example="Weaver WPS example schema.", missing=drop)


class OWSServiceIdentification(WPSDescriptionType, OWSNamespace):
    name = "ServiceIdentification"
    title = "ServiceIdentification"
    keywords = OWSKeywordList(name="Keywords")
    type = OWSType()
    svc_type = OWSString(name="ServiceType", title="ServiceType", example="WPS")
    svc_type_ver1 = OWSString(name="ServiceTypeVersion", title="ServiceTypeVersion", example="1.0.0")
    svc_type_ver2 = OWSString(name="ServiceTypeVersion", title="ServiceTypeVersion", example="2.0.0")
    fees = OWSString(name="Fees", title="Fees", example="NONE", missing=drop, default="NONE")
    access = OWSString(name="AccessConstraints", title="AccessConstraints",
                       example="NONE", missing=drop, default="NONE")
    provider = OWSServiceProvider()


class OWSOperationName(ExtendedSchemaNode, OWSNamespace):
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
    example = "http://schema-example.com/wps"


class OperationRequest(ExtendedMappingSchema, OWSNamespace):
    href = OperationLink()


class OWS_HTTP(ExtendedMappingSchema, OWSNamespace):
    get = OperationRequest(name="Get", title="OWSGet")
    post = OperationRequest(name="Post", title="OWSPost")


class OWS_DCP(ExtendedMappingSchema, OWSNamespace):
    http = OWS_HTTP(name="HTTP", missing=drop)
    https = OWS_HTTP(name="HTTPS", missing=drop)


class Operation(ExtendedMappingSchema, OWSNamespace):
    name = OWSOperationName()
    dcp = OWS_DCP()


class OperationsMetadata(ExtendedSequenceSchema, OWSNamespace):
    name = "OperationsMetadata"
    op = Operation()


class ProcessVersion(ExtendedSchemaNode, WPSNamespace):
    schema_type = String
    attribute = True


class OWSProcessSummary(ExtendedMappingSchema, WPSNamespace):
    version = ProcessVersion(name="processVersion", default="None", example="1.2",
                             description="Version of the corresponding process summary.")
    identifier = OWSIdentifier(example="example", description="Identifier to refer to the process.")
    _title = OWSTitle(example="Example Process", description="Title of the process.")
    abstract = OWSAbstract(example="Process for example schema.", description="Detail about the process.")


class WPSProcessOfferings(ExtendedSequenceSchema, WPSNamespace):
    name = "ProcessOfferings"
    title = "ProcessOfferings"
    process = OWSProcessSummary(name="Process")


class WPSLanguagesType(ExtendedSequenceSchema, WPSNamespace):
    title = "LanguagesType"
    wrapped = False
    lang = OWSLanguage(name="Language")


class WPSLanguageSpecification(ExtendedMappingSchema, WPSNamespace):
    name = "Languages"
    title = "Languages"
    default = OWSLanguage(name="Default")
    supported = WPSLanguagesType(name="Supported")


class WPSResponseBaseType(PermissiveMappingSchema, WPSNamespace):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/common/ResponseBaseType.xsd"
    service = WPSServiceAttribute()
    version = WPSVersionAttribute()
    lang = WPSLanguageAttribute()


class WPSProcessVersion(ExtendedSchemaNode, WPSNamespace):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/common/ProcessVersion.xsd"
    schema_type = String
    description = "Release version of this Process."
    name = "processVersion"
    attribute = True


class WPSInputDescriptionType(WPSDescriptionType):
    identifier = OWSIdentifier(description="Unique identifier of the input.")
    # override below to have different examples/descriptions
    _title = OWSTitle(description="Human readable representation of the process input.")
    abstract = OWSAbstract(missing=drop)
    metadata = OWSMetadata(missing=drop)


class WPSLiteralInputType(ExtendedMappingSchema, XMLObject):
    pass


class WPSLiteralData(WPSLiteralInputType):
    name = "LiteralData"


class WPSCRSsType(ExtendedMappingSchema, WPSNamespace):
    crs = XMLString(name="CRS", description="Coordinate Reference System")


class WPSSupportedCRS(ExtendedSequenceSchema):
    crs = WPSCRSsType(name="CRS")


class WPSSupportedCRSType(ExtendedMappingSchema, WPSNamespace):
    name = "SupportedCRSsType"
    default = WPSCRSsType(name="Default")
    supported = WPSSupportedCRS(name="Supported")


class WPSBoundingBoxData(ExtendedMappingSchema, XMLObject):
    data = WPSSupportedCRSType(name="BoundingBoxData")


class WPSFormatDefinition(ExtendedMappingSchema, XMLObject):
    mime_type = XMLString(name="MimeType", default=ContentType.TEXT_PLAIN, example=ContentType.TEXT_PLAIN)
    encoding = XMLString(name="Encoding", missing=drop, example="base64")
    schema = XMLString(name="Schema", missing=drop)


class WPSFileFormat(ExtendedMappingSchema, XMLObject):
    name = "Format"
    format = WPSFormatDefinition()


class WPSFormatList(ExtendedSequenceSchema):
    format = WPSFileFormat()


class WPSComplexInputType(ExtendedMappingSchema, WPSNamespace):
    max_mb = XMLString(name="maximumMegabytes", attribute=True)
    defaults = WPSFileFormat(name="Default")
    supported = WPSFormatList(name="Supported")


class WPSComplexData(ExtendedMappingSchema, XMLObject):
    data = WPSComplexInputType(name="ComplexData")


class WPSInputFormChoice(OneOfKeywordSchema):
    title = "InputFormChoice"
    _one_of = [
        WPSComplexData(),
        WPSLiteralData(),
        WPSBoundingBoxData(),
    ]


class WPSMinOccursAttribute(MinOccursDefinition, XMLObject):
    name = "minOccurs"
    attribute = True


class WPSMaxOccursAttribute(MinOccursDefinition, XMLObject):
    name = "maxOccurs"
    prefix = drop
    attribute = True


class WPSDataInputDescription(ExtendedMappingSchema):
    min_occurs = WPSMinOccursAttribute()
    max_occurs = WPSMaxOccursAttribute()


class WPSDataInputItem(AllOfKeywordSchema, WPSNamespace):
    _all_of = [
        WPSInputDescriptionType(),
        WPSInputFormChoice(),
        WPSDataInputDescription(),
    ]


class WPSDataInputs(ExtendedSequenceSchema, WPSNamespace):
    name = "DataInputs"
    title = "DataInputs"
    input = WPSDataInputItem()


class WPSOutputDescriptionType(WPSDescriptionType):
    name = "OutputDescriptionType"
    title = "OutputDescriptionType"
    identifier = OWSIdentifier(description="Unique identifier of the output.")
    # override below to have different examples/descriptions
    _title = OWSTitle(description="Human readable representation of the process output.")
    abstract = OWSAbstract(missing=drop)
    metadata = OWSMetadata(missing=drop)


class ProcessOutputs(ExtendedSequenceSchema, WPSNamespace):
    name = "ProcessOutputs"
    title = "ProcessOutputs"
    output = WPSOutputDescriptionType()


class WPSGetCapabilities(WPSResponseBaseType):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsGetCapabilities_response.xsd"
    name = "Capabilities"
    title = "Capabilities"  # not to be confused by 'GetCapabilities' used for request
    svc = OWSServiceIdentification()
    ops = OperationsMetadata()
    offering = WPSProcessOfferings()
    languages = WPSLanguageSpecification()


class WPSProcessDescriptionType(WPSResponseBaseType, WPSProcessVersion):
    name = "ProcessDescriptionType"
    description = "Description of the requested process by identifier."
    store = XMLBooleanAttribute(name="storeSupported", example=True, default=True)
    status = XMLBooleanAttribute(name="statusSupported", example=True, default=True)
    inputs = WPSDataInputs()
    outputs = ProcessOutputs()


class WPSProcessDescriptionList(ExtendedSequenceSchema, WPSNamespace):
    name = "ProcessDescriptions"
    title = "ProcessDescriptions"
    description = "Listing of process description for every requested identifier."
    wrapped = False
    process = WPSProcessDescriptionType()


class WPSDescribeProcess(WPSResponseBaseType):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsDescribeProcess_response.xsd"
    name = "DescribeProcess"
    title = "DescribeProcess"
    process = WPSProcessDescriptionList()


class WPSStatusLocationAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "statusLocation"
    prefix = drop
    attribute = True
    format = "file"


class WPSServiceInstanceAttribute(ExtendedSchemaNode, XMLObject):
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


class WPSStatusSuccess(ExtendedSchemaNode, WPSNamespace):
    schema_type = String
    name = "ProcessSucceeded"
    title = "ProcessSucceeded"


class WPSStatusFailed(ExtendedSchemaNode, WPSNamespace):
    schema_type = String
    name = "ProcessFailed"
    title = "ProcessFailed"


class WPSStatus(ExtendedMappingSchema, WPSNamespace):
    name = "Status"
    title = "Status"
    creationTime = CreationTimeAttribute()
    status_success = WPSStatusSuccess(missing=drop)
    status_failed = WPSStatusFailed(missing=drop)


class WPSProcessSummary(ExtendedMappingSchema, WPSNamespace):
    name = "Process"
    title = "Process"
    identifier = OWSIdentifier()
    _title = OWSTitle()
    abstract = OWSAbstract(missing=drop)


class WPSOutputBase(ExtendedMappingSchema):
    identifier = OWSIdentifier()
    _title = OWSTitle()
    abstract = OWSAbstract(missing=drop)


class WPSOutputDefinitionItem(WPSOutputBase, WPSNamespace):
    name = "Output"
    # use different title to avoid OpenAPI schema definition clash with 'Output' of 'WPSProcessOutputs'
    title = "OutputDefinition"


class WPSOutputDefinitions(ExtendedSequenceSchema, WPSNamespace):
    name = "OutputDefinitions"
    title = "OutputDefinitions"
    out_def = WPSOutputDefinitionItem()


class WPSOutputLiteral(ExtendedMappingSchema):
    data = ()


class WPSReference(ExtendedMappingSchema, WPSNamespace):
    href = XMLReferenceAttribute()
    mimeType = MimeTypeAttribute()
    encoding = EncodingAttribute()


class WPSOutputReference(ExtendedMappingSchema):
    title = "OutputReference"
    reference = WPSReference(name="Reference")


class WPSOutputData(OneOfKeywordSchema):
    _one_of = [
        WPSOutputLiteral(),
        WPSOutputReference(),
    ]


class WPSDataOutputItem(AllOfKeywordSchema, WPSNamespace):
    name = "Output"
    # use different title to avoid OpenAPI schema definition clash with 'Output' of 'WPSOutputDefinitions'
    title = "DataOutput"
    _all_of = [
        WPSOutputBase(),
        WPSOutputData(),
    ]


class WPSProcessOutputs(ExtendedSequenceSchema, WPSNamespace):
    name = "ProcessOutputs"
    title = "ProcessOutputs"
    output = WPSDataOutputItem()


class WPSExecuteResponse(WPSResponseBaseType, WPSProcessVersion):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsExecute_response.xsd"
    name = "ExecuteResponse"
    title = "ExecuteResponse"  # not to be confused by 'Execute' used for request
    location = WPSStatusLocationAttribute()
    svc_loc = WPSServiceInstanceAttribute()
    process = WPSProcessSummary()
    status = WPSStatus()
    inputs = WPSDataInputs(missing=drop)          # when lineage is requested only
    out_def = WPSOutputDefinitions(missing=drop)  # when lineage is requested only
    outputs = WPSProcessOutputs()


class WPSXMLSuccessBodySchema(OneOfKeywordSchema):
    _one_of = [
        WPSGetCapabilities(),
        WPSDescribeProcess(),
        WPSExecuteResponse(),
    ]


class OWSExceptionCodeAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "exceptionCode"
    title = "Exception"
    attribute = True


class OWSExceptionLocatorAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "locator"
    attribute = True


class OWSExceptionText(ExtendedSchemaNode, OWSNamespace):
    schema_type = String
    name = "ExceptionText"


class OWSException(ExtendedMappingSchema, OWSNamespace):
    name = "Exception"
    title = "Exception"
    code = OWSExceptionCodeAttribute(example="MissingParameterValue")
    locator = OWSExceptionLocatorAttribute(default="None", example="service")
    text = OWSExceptionText(example="Missing service")


class OWSExceptionReport(ExtendedMappingSchema, OWSNamespace):
    name = "ExceptionReport"
    title = "ExceptionReport"
    exception = OWSException()


class WPSException(ExtendedMappingSchema):
    report = OWSExceptionReport()


class OkWPSResponse(ExtendedMappingSchema):
    description = "WPS operation successful"
    header = XmlHeader()
    body = WPSXMLSuccessBodySchema()


class ErrorWPSResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred on WPS endpoint."
    header = XmlHeader()
    body = WPSException()


class ProviderEndpoint(ProviderPath):
    header = RequestHeaders()


class ProviderProcessEndpoint(ProviderPath, ProcessPath):
    header = RequestHeaders()


class ProcessEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessPackageEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessPayloadEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessVisibilityGetEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessVisibilityPutEndpoint(ProcessPath):
    header = RequestHeaders()
    body = Visibility()


class ProviderJobEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobEndpoint(JobPath):
    header = RequestHeaders()


class ProcessInputsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class ProviderInputsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobInputsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessOutputsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class ProviderOutputsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobOutputsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessResultEndpoint(ProcessOutputsEndpoint):
    deprecated = True
    header = RequestHeaders()


class ProviderResultEndpoint(ProviderOutputsEndpoint):
    deprecated = True
    header = RequestHeaders()


class JobResultEndpoint(JobOutputsEndpoint):
    deprecated = True
    header = RequestHeaders()


class ProcessResultsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class ProviderResultsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobResultsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class ProviderExceptionsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobExceptionsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessExceptionsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class ProviderLogsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobLogsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessLogsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


##################################################################
# These classes define schemas for requests that feature a body
##################################################################


class CreateProviderRequestBody(ExtendedMappingSchema):
    id = AnyIdentifier()
    url = URL(description="Endpoint where to query the provider.")
    public = ExtendedSchemaNode(Boolean())


class InputDataType(InputIdentifierType):
    pass


class OutputDataType(OutputIdentifierType):
    format = Format(missing=drop)


class Output(OutputDataType):
    transmissionMode = TransmissionModeEnum(missing=drop)


class OutputList(ExtendedSequenceSchema):
    output = Output()


class ProviderSummarySchema(ExtendedMappingSchema):
    """WPS provider summary definition."""
    id = ExtendedSchemaNode(String())
    url = URL(description="Endpoint of the provider.")
    title = ExtendedSchemaNode(String())
    abstract = ExtendedSchemaNode(String())
    public = ExtendedSchemaNode(Boolean())


class ProviderCapabilitiesSchema(ExtendedMappingSchema):
    """WPS provider capabilities."""
    id = ExtendedSchemaNode(String())
    url = URL(description="WPS GetCapabilities URL of the provider.")
    title = ExtendedSchemaNode(String())
    abstract = ExtendedSchemaNode(String())
    contact = ExtendedSchemaNode(String())
    type = ExtendedSchemaNode(String())


class TransmissionModeList(ExtendedSequenceSchema):
    transmissionMode = TransmissionModeEnum()


class JobControlOptionsList(ExtendedSequenceSchema):
    jobControlOption = JobControlOptionsEnum()


class ExceptionReportType(ExtendedMappingSchema):
    code = ExtendedSchemaNode(String())
    description = ExtendedSchemaNode(String(), missing=drop)


class ProcessSummary(ProcessDescriptionType, ProcessDescriptionMeta):
    """WPS process definition."""
    version = Version(missing=drop)
    jobControlOptions = JobControlOptionsList(missing=[])
    outputTransmission = TransmissionModeList(missing=[])
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
    visibility = VisibilityValue(missing=drop)


class ProcessDeployment(ProcessDescriptionType, ProcessDeployMeta):
    # allowed undefined I/O during deploy because of reference from owsContext or executionUnit
    inputs = InputTypeList(
        missing=drop, title="DeploymentInputs",
        description="Additional definitions for process inputs to extend generated details by the referred package. "
                    "These are optional as they can mostly be inferred from the 'executionUnit', but allow specific "
                    "overrides (see '{}/package.html#correspondence-between-cwl-and-wps-fields')".format(DOC_URL))
    outputs = OutputDescriptionList(
        missing=drop, title="DeploymentInputs",
        description="Additional definitions for process outputs to extend generated details by the referred package. "
                    "These are optional as they can mostly be inferred from the 'executionUnit', but allow specific "
                    "overrides (see '{}/package.html#correspondence-between-cwl-and-wps-fields')".format(DOC_URL))
    visibility = VisibilityValue(missing=drop)


class ProcessOutputDescriptionSchema(ExtendedMappingSchema):
    """WPS process output definition."""
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
    status = ExtendedSchemaNode(String(), example=STATUS_ACCEPTED)
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
    mode = JobExecuteModeEnum()
    response = JobResponseOptionsEnum()


class AlternateQuotation(ExtendedMappingSchema):
    id = UUID(description="Quote ID.")
    title = ExtendedSchemaNode(String(), description="Name of the quotation.", missing=drop)
    description = ExtendedSchemaNode(String(), description="Description of the quotation.", missing=drop)
    price = ExtendedSchemaNode(Float(), description="Process execution price.")
    currency = ExtendedSchemaNode(String(), description="Currency code in ISO-4217 format.")
    expire = ExtendedSchemaNode(DateTime(), description="Expiration date and time of the quote in ISO-8601 format.")
    created = ExtendedSchemaNode(DateTime(), description="Creation date and time of the quote in ISO-8601 format.")
    details = ExtendedSchemaNode(String(), description="Details of the quotation.", missing=drop)
    estimatedTime = ExtendedSchemaNode(String(), description="Estimated process execution duration.", missing=drop)


class AlternateQuotationList(ExtendedSequenceSchema):
    step = AlternateQuotation(description="Quote of a workflow step process.")


# same as base Format, but for process/job responses instead of process submission
# (ie: 'Format' is for allowed/supported formats, this is the result format)
class DataEncodingAttributes(Format):
    pass


class Reference(ExtendedMappingSchema):
    title = "Reference"
    href = ReferenceURL(description="Endpoint of the reference.")
    format = DataEncodingAttributes(missing=drop)
    body = ExtendedSchemaNode(String(), missing=drop)
    bodyReference = ReferenceURL(missing=drop)


class AnyType(OneOfKeywordSchema):
    """Permissive variants that we attempt to parse automatically."""
    _one_of = [
        # literal data with 'data' key
        AnyLiteralDataType(),
        # same with 'value' key (OGC specification)
        AnyLiteralValueType(),
        # HTTP references with various keywords
        LiteralReference(),
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
    # permit unspecified inputs for processes that could technically allow no-inputs definition (CWL),
    # but very unlikely/unusual in real world scenarios (possible case: constant endpoint fetcher?)
    inputs = InputList(missing=drop)
    outputs = OutputList()
    mode = JobExecuteModeEnum()
    notification_email = ExtendedSchemaNode(
        String(),
        missing=drop,
        validator=Email(),
        description="Optionally send a notification email when the job is done.")
    response = JobResponseOptionsEnum()


class QuoteProcessListSchema(ExtendedSequenceSchema):
    step = Quotation(description="Quote of a workflow step process.")


class QuoteSchema(ExtendedMappingSchema):
    id = UUID(description="Quote ID.")
    process = AnyIdentifier(description="Corresponding process ID.")
    steps = QuoteProcessListSchema(description="Child processes and prices.")
    total = ExtendedSchemaNode(Float(), description="Total of the quote including step processes.")


class QuotationList(ExtendedSequenceSchema):
    quote = ExtendedSchemaNode(String(), description="Quote ID.")


class QuotationListSchema(ExtendedMappingSchema):
    quotations = QuotationList()


class BillSchema(ExtendedMappingSchema):
    id = UUID(description="Bill ID.")
    title = ExtendedSchemaNode(String(), description="Name of the bill.")
    description = ExtendedSchemaNode(String(), missing=drop)
    price = ExtendedSchemaNode(Float(), description="Price associated to the bill.")
    currency = ExtendedSchemaNode(String(), description="Currency code in ISO-4217 format.")
    created = ExtendedSchemaNode(DateTime(), description="Creation date and time of the bill in ISO-8601 format.")
    userId = ExtendedSchemaNode(Integer(), description="User id that requested the quote.")
    quotationId = UUID(description="Corresponding quote ID.", missing=drop)


class BillList(ExtendedSequenceSchema):
    bill = ExtendedSchemaNode(String(), description="Bill ID.")


class BillListSchema(ExtendedMappingSchema):
    bills = BillList()


class SupportedValues(ExtendedMappingSchema):
    pass


class DefaultValues(ExtendedMappingSchema):
    pass


class CWLClass(ExtendedSchemaNode):
    # in this case it is ok to use 'name' because target fields receiving it will
    # never be able to be named 'class' because of Python reserved keyword
    name = "class"
    title = "Class"
    schema_type = String
    example = "CommandLineTool"
    validator = OneOf(["CommandLineTool", "ExpressionTool", "Workflow"])
    description = (
        "CWL class specification. This is used to differentiate between single Application Package (AP)"
        "definitions and Workflow that chains multiple packages."
    )


class RequirementClass(ExtendedSchemaNode):
    # in this case it is ok to use 'name' because target fields receiving it will
    # never be able to be named 'class' because of Python reserved keyword
    name = "class"
    title = "RequirementClass"
    schema_type = String
    description = "CWL requirement class specification."


class DockerRequirementSpecification(PermissiveMappingSchema):
    dockerPull = ExtendedSchemaNode(
        String(),
        example="docker-registry.host.com/namespace/image:1.2.3",
        title="Docker pull reference",
        description="Reference package that will be retrieved and executed by CWL."
    )


class DockerRequirementMap(ExtendedMappingSchema):
    DockerRequirement = DockerRequirementSpecification(
        name=CWL_REQUIREMENT_APP_DOCKER,
        title=CWL_REQUIREMENT_APP_DOCKER
    )


class DockerRequirementClass(DockerRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_DOCKER, validator=OneOf([CWL_REQUIREMENT_APP_DOCKER]))


class DockerGpuRequirementSpecification(DockerRequirementSpecification):
    description = (
        "Docker requirement with GPU-enabled support (https://github.com/NVIDIA/nvidia-docker). "
        "The instance must have the NVIDIA toolkit installed to use this feature."
    )


class DockerGpuRequirementMap(ExtendedMappingSchema):
    req = DockerGpuRequirementSpecification(name=CWL_REQUIREMENT_APP_DOCKER_GPU)


class DockerGpuRequirementClass(DockerGpuRequirementSpecification):
    title = CWL_REQUIREMENT_APP_DOCKER_GPU
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_DOCKER_GPU, validator=OneOf([CWL_REQUIREMENT_APP_DOCKER_GPU]))


class DirectoryListing(PermissiveMappingSchema):
    entry = ExtendedSchemaNode(String(), missing=drop)


class InitialWorkDirListing(ExtendedSequenceSchema):
    listing = DirectoryListing()


class InitialWorkDirRequirementSpecification(PermissiveMappingSchema):
    listing = InitialWorkDirListing()


class InitialWorkDirRequirementMap(ExtendedMappingSchema):
    req = InitialWorkDirRequirementSpecification(name=CWL_REQUIREMENT_INIT_WORKDIR)


class InitialWorkDirRequirementClass(InitialWorkDirRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_INIT_WORKDIR,
                              validator=OneOf([CWL_REQUIREMENT_INIT_WORKDIR]))


class BuiltinRequirementSpecification(PermissiveMappingSchema):
    title = CWL_REQUIREMENT_APP_BUILTIN
    description = (
        "Hint indicating that the Application Package corresponds to a builtin process of "
        "this instance. (note: can only be an 'hint' as it is unofficial CWL specification)."
    )
    process = AnyIdentifier(description="Builtin process identifier.")


class BuiltinRequirementMap(ExtendedMappingSchema):
    req = BuiltinRequirementSpecification(name=CWL_REQUIREMENT_APP_BUILTIN)


class BuiltinRequirementClass(BuiltinRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_BUILTIN, validator=OneOf([CWL_REQUIREMENT_APP_BUILTIN]))


class ESGF_CWT_RequirementSpecification(PermissiveMappingSchema):
    title = CWL_REQUIREMENT_APP_ESGF_CWT
    description = (
        "Hint indicating that the Application Package corresponds to an ESGF-CWT provider process"
        "that should be remotely executed and monitored by this instance. "
        "(note: can only be an 'hint' as it is unofficial CWL specification)."
    )
    process = AnyIdentifier(description="Process identifier of the remote ESGF-CWT provider.")
    provider = AnyIdentifier(description="ESGF-CWT provider endpoint.")


class ESGF_CWT_RequirementMap(ExtendedMappingSchema):
    req = ESGF_CWT_RequirementSpecification(name=CWL_REQUIREMENT_APP_ESGF_CWT)


class ESGF_CWT_RequirementClass(ESGF_CWT_RequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_ESGF_CWT, validator=OneOf([CWL_REQUIREMENT_APP_ESGF_CWT]))


class WPS1RequirementSpecification(PermissiveMappingSchema):
    title = CWL_REQUIREMENT_APP_WPS1
    description = (
        "Hint indicating that the Application Package corresponds to a WPS-1 provider process"
        "that should be remotely executed and monitored by this instance. "
        "(note: can only be an 'hint' as it is unofficial CWL specification)."
    )
    process = AnyIdentifier(description="Process identifier of the remote WPS provider.")
    provider = AnyIdentifier(description="WPS provider endpoint.")


class WPS1RequirementMap(ExtendedMappingSchema):
    req = WPS1RequirementSpecification(name=CWL_REQUIREMENT_APP_WPS1)


class WPS1RequirementClass(WPS1RequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_WPS1, validator=OneOf([CWL_REQUIREMENT_APP_WPS1]))


class UnknownRequirementClass(PermissiveMappingSchema):
    _class = RequirementClass(example="UnknownRequirement")


class CWLRequirementsMap(AnyOfKeywordSchema):
    _any_of = [
        DockerRequirementMap(missing=drop),
        DockerGpuRequirementMap(missing=drop),
        InitialWorkDirRequirementMap(missing=drop),
        PermissiveMappingSchema(missing=drop),
    ]


class CWLRequirementsItem(OneOfKeywordSchema):
    _one_of = [
        DockerRequirementClass(missing=drop),
        DockerGpuRequirementClass(missing=drop),
        InitialWorkDirRequirementClass(missing=drop),
        UnknownRequirementClass(missing=drop),  # allows anything, must be last
    ]


class CWLRequirementsList(ExtendedSequenceSchema):
    requirement = CWLRequirementsItem()


class CWLRequirements(OneOfKeywordSchema):
    _one_of = [
        CWLRequirementsMap(),
        CWLRequirementsList(),
    ]


class CWLHintsMap(AnyOfKeywordSchema, PermissiveMappingSchema):
    _any_of = [
        BuiltinRequirementMap(missing=drop),
        DockerRequirementMap(missing=drop),
        DockerGpuRequirementMap(missing=drop),
        InitialWorkDirRequirementMap(missing=drop),
        ESGF_CWT_RequirementMap(missing=drop),
        WPS1RequirementMap(missing=drop),
    ]


class CWLHintsItem(OneOfKeywordSchema, PermissiveMappingSchema):
    # validators of individual requirements define which one applies
    # in case of ambiguity, 'discriminator' distinguish between them using their 'example' values in 'class' field
    discriminator = "class"
    _one_of = [
        BuiltinRequirementClass(missing=drop),
        DockerRequirementClass(missing=drop),
        DockerGpuRequirementClass(missing=drop),
        InitialWorkDirRequirementClass(missing=drop),
        ESGF_CWT_RequirementClass(missing=drop),
        WPS1RequirementClass(missing=drop),
        UnknownRequirementClass(missing=drop),  # allows anything, must be last
    ]


class CWLHintsList(ExtendedSequenceSchema):
    hint = CWLHintsItem()


class CWLHints(OneOfKeywordSchema):
    _one_of = [
        CWLHintsMap(),
        CWLHintsList(),
    ]


class CWLArguments(ExtendedSequenceSchema):
    argument = ExtendedSchemaNode(String())


class CWLTypeString(ExtendedSchemaNode):
    schema_type = String
    # in this case it is ok to use 'name' because target fields receiving it will
    # cause issues against builtin 'type' of Python reserved keyword
    title = "Type"
    description = "Field type definition."
    example = "float"
    validator = OneOf(PACKAGE_TYPE_POSSIBLE_VALUES)


class CWLTypeSymbolValues(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(Float()),
        ExtendedSchemaNode(Integer()),
        ExtendedSchemaNode(String()),
    ]


class CWLTypeSymbols(ExtendedSequenceSchema):
    symbol = CWLTypeSymbolValues()


class CWLTypeArray(ExtendedMappingSchema):
    type = ExtendedSchemaNode(String(), example=PACKAGE_ARRAY_BASE, validator=OneOf([PACKAGE_ARRAY_BASE]))
    items = CWLTypeString(title="CWLTypeArrayItems", validator=OneOf(PACKAGE_ARRAY_ITEMS))


class CWLTypeEnum(ExtendedMappingSchema):
    type = ExtendedSchemaNode(String(), example=PACKAGE_ENUM_BASE, validator=OneOf(PACKAGE_CUSTOM_TYPES))
    symbols = CWLTypeSymbols(summary="Allowed values composing the enum.")


class CWLTypeBase(OneOfKeywordSchema):
    _one_of = [
        CWLTypeString(summary="CWL type as literal value."),
        CWLTypeArray(summary="CWL type as list of items."),
        CWLTypeEnum(summary="CWL type as enum of values."),
    ]


class CWLTypeList(ExtendedSequenceSchema):
    type = CWLTypeBase()


class CWLType(OneOfKeywordSchema):
    title = "CWL Type"
    _one_of = [
        CWLTypeBase(summary="CWL type definition."),
        CWLTypeList(summary="Combination of allowed CWL types."),
    ]


class AnyLiteralList(ExtendedSequenceSchema):
    default = AnyLiteralType()


class CWLDefault(OneOfKeywordSchema):
    _one_of = [
        AnyLiteralType(),
        AnyLiteralList(),
    ]


class CWLInputObject(PermissiveMappingSchema):
    type = CWLType()
    default = CWLDefault(missing=drop, description="Default value of input if not provided for task execution.")
    inputBinding = ExtendedMappingSchema(missing=drop, title="Input Binding",
                                         description="Defines how to specify the input for the command.")


class CWLTypeStringList(ExtendedSequenceSchema):
    description = "List of allowed direct CWL type specifications as strings."
    type = CWLType()


class CWLInputType(OneOfKeywordSchema):
    description = "CWL type definition of the input."
    _one_of = [
        CWLTypeString(summary="Direct CWL type string specification."),
        CWLTypeStringList(summary="List of allowed CWL type strings."),
        CWLInputObject(summary="CWL type definition with parameters."),
    ]


class CWLInputMap(PermissiveMappingSchema):
    input_id = CWLInputType(variable="<input-id>", title="CWLInputIdentifierType",
                            description=IO_INFO_IDS.format(first="CWL", second="WPS", what="input") +
                            " (Note: '<input-id>' is a variable corresponding for each identifier)")


class InputItem(CWLInputObject):
    id = AnyIdentifier(description="Some ID")


class CWLInputList(ExtendedSequenceSchema):
    input = InputItem(title="Input", description="Input specification.")


class InputsDefinition(OneOfKeywordSchema):
    _one_of = [
        CWLInputList(description="Package inputs defined as items."),
        CWLInputMap(description="Package inputs defined as mapping."),
    ]


class OutputBinding(PermissiveMappingSchema):
    glob = ExtendedSchemaNode(String(), missing=drop,
                              description="Glob pattern the will find the output on disk or mounted docker volume.")


class CWLOutputObject(PermissiveMappingSchema):
    type = CWLType()
    # 'outputBinding' should usually be there most of the time (if not always) to retrieve file,
    # but can technically be omitted in some very specific use-cases such as output literal or output is std logs
    outputBinding = OutputBinding(
        missing=drop,
        description="Defines how to retrieve the output result from the command."
    )


class CWLOutputType(OneOfKeywordSchema):
    _one_of = [
        CWLTypeString(summary="Direct CWL type string specification."),
        CWLTypeStringList(summary="List of allowed CWL type strings."),
        CWLOutputObject(summary="CWL type definition with parameters."),
    ]


class CWLOutputMap(ExtendedMappingSchema):
    output_id = CWLOutputType(variable="<output-id>", title="CWLOutputIdentifierType",
                              description=IO_INFO_IDS.format(first="CWL", second="WPS", what="output") +
                              " (Note: '<output-id>' is a variable corresponding for each identifier)")


class CWLOutputItem(CWLOutputObject):
    id = AnyIdentifier(description=IO_INFO_IDS.format(first="CWL", second="WPS", what="output"))


class CWLOutputList(ExtendedSequenceSchema):
    input = CWLOutputItem(description="Output specification. " + CWL_DOC_MESSAGE)


class CWLOutputsDefinition(OneOfKeywordSchema):
    _one_of = [
        CWLOutputList(description="Package outputs defined as items."),
        CWLOutputMap(description="Package outputs defined as mapping."),
    ]


class CWLCommandParts(ExtendedSequenceSchema):
    cmd = ExtendedSchemaNode(String())


class CWLCommand(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(String(), title="String command."),
        CWLCommandParts(title="Command Parts")
    ]


class CWLVersion(Version):
    description = "CWL version of the described application package."
    example = CWL_VERSION
    validator = SemanticVersion(v_prefix=True, rc_suffix=False)


class CWL(PermissiveMappingSchema):
    cwlVersion = CWLVersion()
    _class = CWLClass()
    requirements = CWLRequirements(description="Explicit requirement to execute the application package.", missing=drop)
    hints = CWLHints(description="Non-failing additional hints that can help resolve extra requirements.", missing=drop)
    baseCommand = CWLCommand(description="Command called in the docker image or on shell according to requirements "
                                         "and hints specifications. Can be omitted if already defined in the "
                                         "docker image.", missing=drop)
    arguments = CWLArguments(description="Base arguments passed to the command.", missing=drop)
    inputs = InputsDefinition(description="All inputs available to the Application Package.")
    outputs = CWLOutputsDefinition(description="All outputs produced by the Application Package.")


class Unit(ExtendedMappingSchema):
    unit = CWL(description="Execution unit definition as CWL package specification. " + CWL_DOC_MESSAGE)


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


# implement only literal part of:
#   https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/core/openapi/schemas/inlineOrRefData.yaml
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
    schema_ref = "{}/master/core/openapi/schemas/result.yaml".format(OGC_API_SCHEMA_URL)
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
    example_ref = "{}/master/core/examples/json/Result.json".format(OGC_API_SCHEMA_URL)
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
    # note: test fields correspond exactly to 'owslib.wps.WPSException', they are deserialized as is
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
    url = URL(description="Referenced parameter endpoint.", example="https://weaver-host", missing=drop)
    doc = ExtendedSchemaNode(String(), example="https://weaver-host/api", missing=drop)


class FrontpageParameters(ExtendedSequenceSchema):
    parameter = FrontpageParameterSchema()


class FrontpageSchema(ExtendedMappingSchema):
    message = ExtendedSchemaNode(String(), default="Weaver Information", example="Weaver Information")
    configuration = ExtendedSchemaNode(String(), default="default", example="default")
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
                      example="http://www.opengis.net/spec/WPS/2.0/req/service/binding/rest-json/core")


class ConformanceSchema(ExtendedMappingSchema):
    conformsTo = ConformanceList()


#################################################################
# Local Processes schemas
#################################################################


class PackageBody(ExtendedMappingSchema):
    pass


class ExecutionUnit(OneOfKeywordSchema):
    _one_of = [
        Reference(name="Reference", title="Reference", description="Execution Unit reference."),
        Unit(name="Unit", title="Unit", description="Execution Unit definition."),
    ]


class ExecutionUnitList(ExtendedSequenceSchema):
    unit = ExecutionUnit(
        name="ExecutionUnit",
        title="ExecutionUnit",
        description="Definition of the Application Package to execute."
    )


class Process(ExtendedMappingSchema):
    name = ExtendedSchemaNode(String())
    id = AnyIdentifier()
    version = Version(missing=null)
    created = ExtendedSchemaNode(DateTime(), description="Creation date and time of the quote in ISO-8601 format.")


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
    process = AnyIdentifier(missing=None)
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


class GetProviderJobsEndpoint(GetJobsRequest, ProviderPath, ProcessPath):
    pass


class GetProcessJobEndpoint(ProcessPath):
    header = RequestHeaders()


class DeleteProcessJobEndpoint(ProcessPath):
    header = RequestHeaders()


class BillsEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class BillEndpoint(BillPath):
    header = RequestHeaders()


class ProcessQuotesEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessQuoteEndpoint(ProcessPath, QuotePath):
    header = RequestHeaders()


class GetQuotesQueries(ExtendedMappingSchema):
    page = ExtendedSchemaNode(Integer(), missing=drop, default=0)
    limit = ExtendedSchemaNode(Integer(), missing=drop, default=10)
    process = AnyIdentifier(missing=None)
    sort = QuoteSortEnum(missing=drop)


class QuotesEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()
    querystring = GetQuotesQueries()


class QuoteEndpoint(QuotePath):
    header = RequestHeaders()


class PostProcessQuote(ProcessPath, QuotePath):
    header = RequestHeaders()
    body = NoContent()


class PostQuote(QuotePath):
    header = RequestHeaders()
    body = NoContent()


class PostProcessQuoteRequestEndpoint(ProcessPath, QuotePath):
    header = RequestHeaders()
    body = QuoteProcessParametersSchema()


# ################################################################
# Provider Processes schemas
# ################################################################


class GetProviders(ExtendedMappingSchema):
    header = RequestHeaders()


class PostProvider(ExtendedMappingSchema):
    header = RequestHeaders()
    body = CreateProviderRequestBody()


class GetProviderProcesses(ExtendedMappingSchema):
    header = RequestHeaders()


class GetProviderProcess(ExtendedMappingSchema):
    header = RequestHeaders()


class PostProviderProcessJobRequest(ExtendedMappingSchema):
    """Launching a new process request definition."""
    header = RequestHeaders()
    querystring = LaunchJobQuerystring()
    body = Execute()


# ################################################################
# Responses schemas
# ################################################################

class ErrorDetail(ExtendedMappingSchema):
    code = ExtendedSchemaNode(Integer(), description="HTTP status code.", example=400)
    status = ExtendedSchemaNode(String(), description="HTTP status detail.", example="400 Bad Request")


class OWSErrorCode(ExtendedSchemaNode):
    schema_type = String
    example = "InvalidParameterValue"
    description = "OWS error code."


class OWSExceptionResponse(ExtendedMappingSchema):
    """Error content in XML format"""
    description = "OWS formatted exception."
    code = OWSErrorCode(example="NoSuchProcess")
    locator = ExtendedSchemaNode(String(), example="identifier",
                                 description="Indication of the element that caused the error.")
    message = ExtendedSchemaNode(String(), example="Invalid process ID.",
                                 description="Specific description of the error.")


class ErrorJsonResponseBodySchema(ExtendedMappingSchema):
    code = OWSErrorCode()
    description = ExtendedSchemaNode(String(), description="Detail about the cause of error.")
    error = ErrorDetail(missing=drop)
    exception = OWSExceptionResponse(missing=drop)


class ForbiddenProcessAccessResponseSchema(ExtendedMappingSchema):
    description = "Referenced process is not accessible."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class ForbiddenProviderAccessResponseSchema(ExtendedMappingSchema):
    description = "Referenced provider is not accessible."
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
    providers = ExtendedSchemaNode(
        Boolean(), example=True, default=False, missing=drop,
        description="List local processes as well as all sub-processes of all registered providers. "
                    "Applicable only for Weaver in {} mode, false otherwise.".format(WEAVER_CONFIGURATION_EMS))
    detail = ExtendedSchemaNode(
        Boolean(), example=True, default=True, missing=drop,
        description="Return summary details about each process, or simply their IDs."
    )


class GetProcessesEndpoint(ExtendedMappingSchema):
    querystring = GetProcessesQuery()


class OkGetProcessesListResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessCollection()


class OkPostProcessDeployBodySchema(ExtendedMappingSchema):
    deploymentDone = ExtendedSchemaNode(Boolean(), default=False, example=True,
                                        description="Indicates if the process was successfully deployed.")
    processSummary = ProcessSummary(missing=drop, description="Deployed process summary if successful.")
    failureReason = ExtendedSchemaNode(String(), missing=drop,
                                       description="Description of deploy failure if applicable.")


class OkPostProcessesResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = OkPostProcessDeployBodySchema()


class BadRequestGetProcessInfoResponse(ExtendedMappingSchema):
    description = "Missing process identifier."
    body = NoContent()


class OkGetProcessInfoResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessOffering()


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


class CreatedQuoteExecuteResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = CreatedQuotedJobStatusSchema()


class CreatedQuoteRequestResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = QuoteSchema()


class OkGetQuoteInfoResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = QuoteSchema()


class OkGetQuoteListResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = QuotationListSchema()


class OkGetBillDetailResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = BillSchema()


class OkGetBillListResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = BillListSchema()


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
            "summary": "Listing of local processes registered in Weaver.",
            "value": EXAMPLES["local_process_listing.json"],
        }
    }),
    "500": InternalServerErrorResponseSchema(),
}
post_processes_responses = {
    "201": OkPostProcessesResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_process_responses = {
    "200": OkGetProcessInfoResponse(description="success", examples={
        "ProcessDescription": {
            "summary": "Description of a local process registered in Weaver.",
            "value": EXAMPLES["local_process_description.json"],
        }
    }),
    "400": BadRequestGetProcessInfoResponse(),
    "500": InternalServerErrorResponseSchema(),
}
get_process_package_responses = {
    "200": OkGetProcessPackageSchema(description="success", examples={
        "PackageCWL": {
            "summary": "CWL Application Package definition of the local process.",
            "value": EXAMPLES["local_process_package.json"],
        }
    }),
    "403": ForbiddenProcessAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_process_payload_responses = {
    "200": OkGetProcessPayloadSchema(description="success", examples={
        "Payload": {
            "summary": "Payload employed during process deployment and registration.",
            "value": EXAMPLES["local_process_payload.json"],
        }
    }),
    "403": ForbiddenProcessAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_process_visibility_responses = {
    "200": OkGetProcessVisibilitySchema(description="success"),
    "403": ForbiddenProcessAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
put_process_visibility_responses = {
    "200": OkPutProcessVisibilitySchema(description="success"),
    "403": ForbiddenVisibilityUpdateResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
delete_process_responses = {
    "200": OkDeleteProcessResponse(description="success"),
    "403": ForbiddenProcessAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_providers_list_responses = {
    "200": OkGetProvidersListResponse(description="success", examples={
        "ProviderList": {
            "summary": "Listing of registered remote providers.",
            "value": EXAMPLES["provider_listing.json"],
        }
    }),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_provider_responses = {
    "200": OkGetProviderCapabilitiesSchema(description="success", examples={
        "ProviderDescription": {
            "summary": "Description of a registered remote WPS provider.",
            "value": EXAMPLES["provider_description.json"],
        }
    }),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
delete_provider_responses = {
    "204": NoContentDeleteProviderSchema(description="success"),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
    "501": NotImplementedDeleteProviderResponse(),
}
get_provider_processes_responses = {
    "200": OkGetProviderProcessesSchema(description="success"),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_provider_process_responses = {
    "200": OkGetProviderProcessDescriptionResponse(description="success", examples={
        "ProviderProcessWPS": {
            "summary": "Description of a remote WPS provider process converted to OGC-API Processes format.",
            "value": EXAMPLES["provider_process_description.json"]
        }
    }),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_jobs_responses = {
    "200": OkGetQueriedJobsResponse(description="success", examples={
        "JobListing": {
            "summary": "Job ID listing with default queries.",
            # detailed examples!
            "value": {
                "jobs": [
                    "a9d14bf4-84e0-449a-bac8-16e598efe807",
                    "84e0a9f5-498a-2345-1244-afe54a234cb1"
                ]
            }
        }
    }),
    "500": InternalServerErrorResponseSchema(),
}
get_single_job_status_responses = {
    "200": OkGetJobStatusResponse(description="success", examples={
        "JobStatusSuccess": {
            "summary": "Successful job status response.",
            "value": EXAMPLES["job_status_success.json"]},
        "JobStatusFailure": {
            "summary": "Failed job status response.",
            "value": EXAMPLES["job_status_failed.json"],
        }
    }),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
delete_job_responses = {
    "200": OkDismissJobResponse(description="success"),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_job_inputs_responses = {
    "200": OkGetJobInputsResponse(description="success", examples={
        "JobInputs": {
            "summary": "Submitted job input values at for process execution.",
            "value": EXAMPLES["job_inputs.json"],
        }
    }),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_job_outputs_responses = {
    "200": OkGetJobOutputsResponse(description="success", examples={
        "JobOutputs": {
            "summary": "Obtained job outputs values following process execution.",
            "value": EXAMPLES["job_outputs.json"],
        }
    }),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_result_redirect_responses = {
    "308": RedirectResultResponse(description="Redirects '/result' (without 's') to corresponding '/results' path."),
}
get_job_results_responses = {
    "200": OkGetJobResultsResponse(description="success", examples={
        "JobResults": {
            "summary": "Obtained job results.",
            "value": EXAMPLES["job_results.json"],
        }
    }),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_exceptions_responses = {
    "200": OkGetJobExceptionsResponse(description="success", examples={
        "JobExceptions": {
            "summary": "Job exceptions that occurred during failing process execution.",
            "value": EXAMPLES["job_exceptions.json"],
        }
    }),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_logs_responses = {
    "200": OkGetJobLogsResponse(description="success", examples={
        "JobLogs": {
            "summary": "Job logs registered and captured throughout process execution.",
            "value": EXAMPLES["job_logs.json"],
        }
    }),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_quote_list_responses = {
    "200": OkGetQuoteListResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_quote_responses = {
    "200": OkGetQuoteInfoResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
post_quotes_responses = {
    "201": CreatedQuoteRequestResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
post_quote_responses = {
    "201": CreatedQuoteExecuteResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_bill_list_responses = {
    "200": OkGetBillListResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_bill_responses = {
    "200": OkGetBillDetailResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
wps_responses = {
    "200": OkWPSResponse(examples={
        "GetCapabilities": {
            "summary": "GetCapabilities example response.",
            "value": EXAMPLES["wps_getcapabilities.xml"]
        },
        "DescribeProcess": {
            "summary": "DescribeProcess example response.",
            "value": EXAMPLES["wps_describeprocess.xml"]
        },
        "Execute": {
            "summary": "Execute example response.",
            "value": EXAMPLES["wps_execute_response.xml"]
        }
    }),
    "400": ErrorWPSResponse(examples={
        "MissingParameterError": {
            "summary": "Error report in case of missing request parameter.",
            "value": EXAMPLES["wps_missing_parameter.xml"],
        }
    }),
    "500": ErrorWPSResponse(),
}


##################################
# Define some test data
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

    @api_frontpage_service.get(tags=[TAG_API], response_schemas=get_api_frontpage_responses)
    def  get_api(self, request):

    @processes_service.get(tags=[TAG_PROCESSES], response_schemas=get_processes_responses)
    def get_processes(self, request):
        """Get the list of processes."""
        detail = request.param("detail", False)
        if detail:
            return _PROCESSES
        return [proc["name"] for proc in _PROCESSES]

    @processes_service.post(tags=[TAG_PROCESSES], schema=Deploy(), response_schemas=post_processes_responses)
    def create_processes(self, request):
        """Create a new process."""
        body = {}
        if "name" not in body:
            raise HTTPBadRequest("missing the name!")
        if "name" in _PROCESSES:
            raise HTTPConflict("process name already exist")
        body["created"] = datetime.datetime.now().isoformat().split(".")[0]
        _PROCESSES[body["name"]] = body
        return HTTPCreated("process deployed")

    @process_service.get(tags=[TAG_PROCESSES], response_schemas=get_process_responses)
    def get_process(self, request):
        """Get a single process."""
        process = request.matchdict['process_id']
        if process not in _PROCESSES:
            raise HTTPNotFound("process not found")
        return _PROCESSES[process]

    @job_service.get(tags=[TAG_JOBS], response_schemas=get_job_responses)
    def get_job(self, request):
        """Retrieve some job by UUID."""
        job_id = request.matchdict("job_id")
        if not job_id:
            raise HTTPBadRequest("invalid job id")
        if job_id not in _JOBS:
            raise HTTPNotFound(json={
                "id": "11111111-2222-3333-4444-555555555555",
                "msg": "job does not exist"
            })
        return _JOBS[job_id]


def setup():
    config = Configurator()
    config.include('cornice')
    config.include('cornice_swagger')
    # Create views to serve our OpenAPI spec
    config.cornice_enable_openapi_view(
        api_path="/json",
        title='DemoProcessJobAPI',
        description="OpenAPI documentation",
        version="1.0.0"
    )
    # Create views to serve OpenAPI spec UI explorer
    config.cornice_enable_openapi_explorer(api_explorer_path='/api-explorer')
    config.scan()
    app = config.make_wsgi_app()
    return app


if __name__ == '__main__':
    app = setup()
    server = make_server('127.0.0.1', 8001, app)
    print('Visit me on http://127.0.0.1:8001')
    print('''You can see the API explorer here:
    http://127.0.0.1:8001/api-explorer''')
    server.serve_forever()
