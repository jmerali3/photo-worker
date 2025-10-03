import logging
from botocore.exceptions import ClientError
from temporalio import activity

from worker.models import OcrInput, OcrResult
from worker.utils.s3 import S3Helper
from worker.utils.aws import create_boto3_session
from worker.config import load_config

logger = logging.getLogger(__name__)


@activity.defn
async def ocr_textract(input_data: OcrInput) -> OcrResult:
    """
    Run AWS Textract OCR on the specified S3 object.

    This activity:
    1. Calls AWS Textract detect_document_text (sync API for MVP)
    2. Stores the full OCR JSON response in S3 at artifacts/{job_id}/textract.json
    3. Counts pages/blocks for metadata
    4. Returns OcrResult with S3 key and metadata

    This is idempotent - the S3 key is deterministic based on job_id,
    so re-running will overwrite with the same content.
    """
    config = load_config()

    # Initialize AWS clients
    session = create_boto3_session(
        region=config.aws.region,
        profile_name=config.aws.profile_name,
    )
    textract_client = session.client('textract')

    s3_helper = S3Helper(
        region=config.aws.region,
        profile_name=config.aws.profile_name,
    )

    # Get job_id from activity info for deterministic S3 key
    activity_info = activity.info()
    workflow_id = activity_info.workflow_id
    job_id = workflow_id  # Assuming workflow_id is the job_id

    logger.info(f"Starting Textract OCR for s3://{input_data.bucket}/{input_data.key}")

    try:
        # Call Textract detect_document_text (synchronous)
        response = textract_client.detect_document_text(
            Document={
                'S3Object': {
                    'Bucket': input_data.bucket,
                    'Name': input_data.key
                }
            }
        )

        # Count pages (Textract returns one page for images, multiple for PDFs)
        page_count = 1
        if 'DocumentMetadata' in response and 'Pages' in response['DocumentMetadata']:
            page_count = response['DocumentMetadata']['Pages']

        # Get Textract version info
        ocr_version = response.get('DetectDocumentTextModelVersion', 'unknown')

        # Create deterministic S3 key for OCR output
        ocr_s3_key = f"artifacts/{job_id}/textract.json"

        # Store full Textract response in S3
        ocr_data = {
            'textract_response': response,
            'source_bucket': input_data.bucket,
            'source_key': input_data.key,
            'job_id': job_id,
            'ocr_engine': input_data.engine,
            'ocr_version': ocr_version,
            'page_count': page_count
        }

        success = s3_helper.put_json_object(config.s3.bucket, ocr_s3_key, ocr_data)
        if not success:
            raise RuntimeError(f"Failed to store OCR results to s3://{config.s3.bucket}/{ocr_s3_key}")

        result = OcrResult(
            ocr_engine=input_data.engine,
            ocr_version=ocr_version,
            s3_ocr_key=ocr_s3_key,
            page_count=page_count
        )

        logger.info(
            f"Successfully completed Textract OCR for s3://{input_data.bucket}/{input_data.key}. "
            f"Results stored at s3://{config.s3.bucket}/{ocr_s3_key} "
            f"(pages: {page_count}, version: {ocr_version})"
        )

        return result

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"Textract API error ({error_code}): {error_message}")

        # Handle specific Textract errors
        if error_code == 'InvalidS3ObjectException':
            raise ValueError(f"Invalid S3 object for Textract: s3://{input_data.bucket}/{input_data.key}")
        elif error_code == 'UnsupportedDocumentException':
            raise ValueError(f"Unsupported document type for Textract: s3://{input_data.bucket}/{input_data.key}")
        elif error_code == 'DocumentTooLargeException':
            raise ValueError(f"Document too large for Textract: s3://{input_data.bucket}/{input_data.key}")
        else:
            raise RuntimeError(f"Textract API error: {error_message}")

    except Exception as e:
        logger.error(f"Unexpected error during Textract OCR: {e}")
        raise RuntimeError(f"Failed to process OCR for s3://{input_data.bucket}/{input_data.key}: {str(e)}")
