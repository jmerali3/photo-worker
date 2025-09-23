import logging
from temporalio import activity

from worker.models import TaggingInput, TaggingResult
from worker.utils.s3 import S3Helper
from worker.utils.db import DatabaseHelper
from worker.config import load_config

logger = logging.getLogger(__name__)


@activity.defn
async def tag_from_ocr(input_data: TaggingInput) -> TaggingResult:
    """
    Run LLM tagging on OCR results (future implementation).

    This activity:
    1. Loads OCR JSON from S3
    2. Runs LLM to generate structured tags based on schema_version
    3. Stores tags JSON in S3 at tags/{job_id}/v{schema_version}.json
    4. Upserts recipe_tags record in Postgres
    5. Returns TaggingResult with tags S3 key

    This allows re-tagging without re-running OCR by using different schema_versions.
    """
    config = load_config()

    logger.info(
        f"Starting LLM tagging for job {input_data.job_id} "
        f"(schema v{input_data.schema_version})"
    )

    # Initialize helpers
    s3_helper = S3Helper(
        region=config.aws.region,
        aws_access_key_id=config.aws.access_key_id,
        aws_secret_access_key=config.aws.secret_access_key
    )

    db_helper = DatabaseHelper(config.database)
    db_helper.initialize_pool()

    try:
        # Load OCR JSON from S3
        ocr_data = s3_helper.get_json_object(config.s3.bucket, input_data.ocr_s3_key)
        if not ocr_data:
            raise ValueError(f"OCR data not found at s3://{config.s3.bucket}/{input_data.ocr_s3_key}")

        # TODO: Implement LLM tagging logic here
        # For now, create a placeholder tags structure
        tags_data = {
            'job_id': input_data.job_id,
            'schema_version': input_data.schema_version,
            'source_ocr_key': input_data.ocr_s3_key,
            'tags': {
                'placeholder': True,
                'message': 'LLM tagging not yet implemented',
                'extracted_text_length': len(str(ocr_data.get('textract_response', {}))),
            },
            'generated_at': '2024-01-01T00:00:00Z'  # TODO: Use actual timestamp
        }

        # Create deterministic S3 key for tags
        tags_s3_key = f"tags/{input_data.job_id}/v{input_data.schema_version}.json"

        # Store tags in S3
        tags_success = s3_helper.put_json_object(config.s3.bucket, tags_s3_key, tags_data)
        if not tags_success:
            raise RuntimeError(f"Failed to store tags for job {input_data.job_id}")

        # TODO: Implement recipe_tags table upsert
        # db_helper.upsert_recipe_tags(
        #     recipe_id=input_data.job_id,
        #     schema_version=input_data.schema_version,
        #     s3_tags_key=tags_s3_key
        # )

        result = TaggingResult(s3_tags_key=tags_s3_key)

        logger.info(
            f"Successfully created placeholder tags for job {input_data.job_id} "
            f"at s3://{config.s3.bucket}/{tags_s3_key}"
        )

        return result

    except Exception as e:
        logger.error(f"Failed to generate tags for job {input_data.job_id}: {e}")
        raise RuntimeError(f"Tagging failed for job {input_data.job_id}: {str(e)}")

    finally:
        try:
            db_helper.close_pool()
        except Exception as cleanup_error:
            logger.warning(f"Error closing database pool: {cleanup_error}")