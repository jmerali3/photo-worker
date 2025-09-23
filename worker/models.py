from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel
from datetime import datetime


class WorkflowInput(BaseModel):
    job_id: str
    bucket: str
    key: str
    expected_content_type: Optional[str] = None


class LocateAssetInput(BaseModel):
    bucket: str
    key: str
    expected_content_type: Optional[str] = None


class LocatedAsset(BaseModel):
    bucket: str
    key: str
    content_type: str
    size_bytes: int
    sha256: str


class OcrInput(BaseModel):
    bucket: str
    key: str
    engine: Literal["textract"] = "textract"


class OcrResult(BaseModel):
    ocr_engine: str
    ocr_version: str
    s3_ocr_key: str
    page_count: int


class PersistInput(BaseModel):
    job_id: str
    s3_raw_key: str
    sha256: str
    ocr_s3_key: str
    ocr_engine: str
    ocr_version: str
    page_count: int


class PersistResult(BaseModel):
    recipe_id: str
    manifest_s3_key: str


class TaggingInput(BaseModel):
    job_id: str
    ocr_s3_key: str
    schema_version: int


class TaggingResult(BaseModel):
    s3_tags_key: str


class WorkflowResult(BaseModel):
    job_id: str
    status: str
    recipe_id: str
    s3_raw_key: str
    sha256: str
    ocr_s3_key: str
    manifest_s3_key: str
    page_count: int
    created_at: datetime