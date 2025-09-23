import logging
from datetime import datetime
from temporalio import activity

from worker.models import PersistInput, PersistResult
from worker.utils.db import DatabaseHelper
from worker.utils.s3 import S3Helper
from worker.config import load_config

logger = logging.getLogger(__name__)


@activity.defn
async def persist_artifacts(input_data: PersistInput) -> PersistResult:
    """
    Persist OCR artifacts and metadata to Postgres and S3.

    This activity:
    1. Upserts recipe record in Postgres (recipes table)
    2. Upserts OCR metadata in Postgres (recipe_ocr table)
    3. Creates and stores a manifest JSON in S3
    4. Returns PersistResult with manifest location

    This is idempotent - uses ON CONFLICT DO UPDATE patterns in Postgres
    and deterministic S3 keys for the manifest.
    """
    config = load_config()

    # Initialize database helper
    db_helper = DatabaseHelper(config.database)
    db_helper.initialize_pool()

    # Initialize S3 helper
    s3_helper = S3Helper(
        region=config.aws.region,
        aws_access_key_id=config.aws.access_key_id,
        aws_secret_access_key=config.aws.secret_access_key
    )

    try:
        logger.info(f"Persisting artifacts for job {input_data.job_id}")

        # Upsert recipe record
        recipe_success = db_helper.upsert_recipe(
            recipe_id=input_data.job_id,
            s3_raw_key=input_data.s3_raw_key,
            content_sha256=input_data.sha256,
            status='succeeded'
        )

        if not recipe_success:
            raise RuntimeError(f"Failed to upsert recipe record for job {input_data.job_id}")

        # Upsert OCR metadata
        ocr_success = db_helper.upsert_recipe_ocr(
            recipe_id=input_data.job_id,
            s3_ocr_key=input_data.ocr_s3_key,
            ocr_engine=input_data.ocr_engine,
            ocr_version=input_data.ocr_version,
            page_count=input_data.page_count
        )

        if not ocr_success:
            raise RuntimeError(f"Failed to upsert OCR record for job {input_data.job_id}")

        # Create manifest JSON
        manifest_s3_key = f"artifacts/{input_data.job_id}/manifest.json"
        manifest_data = {
            'job_id': input_data.job_id,
            'recipe_id': input_data.job_id,  # Using job_id as recipe_id
            's3_raw_key': input_data.s3_raw_key,
            'content_sha256': input_data.sha256,
            'ocr_s3_key': input_data.ocr_s3_key,
            'ocr_engine': input_data.ocr_engine,
            'ocr_version': input_data.ocr_version,
            'page_count': input_data.page_count,
            'status': 'succeeded',
            'created_at': datetime.utcnow().isoformat(),
            'manifest_version': '1.0'
        }

        # Store manifest in S3
        manifest_success = s3_helper.put_json_object(
            config.s3.bucket,
            manifest_s3_key,
            manifest_data
        )

        if not manifest_success:
            raise RuntimeError(f"Failed to store manifest for job {input_data.job_id}")

        result = PersistResult(
            recipe_id=input_data.job_id,
            manifest_s3_key=manifest_s3_key
        )

        logger.info(
            f"Successfully persisted artifacts for job {input_data.job_id}. "
            f"Manifest stored at s3://{config.s3.bucket}/{manifest_s3_key}"
        )

        return result

    except Exception as e:
        logger.error(f"Failed to persist artifacts for job {input_data.job_id}: {e}")

        # Try to update recipe status to failed
        try:
            db_helper.upsert_recipe(
                recipe_id=input_data.job_id,
                s3_raw_key=input_data.s3_raw_key,
                content_sha256=input_data.sha256,
                status='failed'
            )
        except Exception as db_error:
            logger.error(f"Failed to update recipe status to failed: {db_error}")

        raise RuntimeError(f"Persistence failed for job {input_data.job_id}: {str(e)}")

    finally:
        # Clean up database connection pool
        try:
            db_helper.close_pool()
        except Exception as cleanup_error:
            logger.warning(f"Error closing database pool: {cleanup_error}")