"""Request/response models for the API."""

from pydantic import BaseModel


class ApplicationData(BaseModel):
    """What the applicant typed into the TTB application form."""

    brand_name: str
    class_type: str
    abv: float
    net_contents: str
    name_address: str
    beverage_type: str = "distilled_spirits"  # "distilled_spirits" | "wine" | "beer"
    is_imported: bool = False
    country_of_origin: str = ""  # imports only


class ExtractedLabelData(BaseModel):
    """What the vision model reads off the label image itself."""

    brand_name: str
    class_type: str
    abv: float
    net_contents: str
    name_address: str
    warning_text: str
    warning_all_caps_bold: bool
    country_of_origin: str = ""


class FieldResultOut(BaseModel):
    field: str
    status: str
    application_value: str
    extracted_value: str
    detail: str = ""


class VerificationResult(BaseModel):
    filename: str
    overall_status: str
    fields: list[FieldResultOut]
    error: str | None = None
