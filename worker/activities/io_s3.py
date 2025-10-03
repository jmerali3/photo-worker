import logging
from temporalio import activity

from worker.models import LocateAssetInput, LocatedAsset
from worker.utils.s3 import S3Helper
from worker.config import load_config

logger = logging.getLogger(__name__)


@activity.defn
async def verify_and_locate_asset(input_data: LocateAssetInput) -> LocatedAsset:
    """
    Verify that the asset exists in S3 and return its metadata.

    This activity:
    1. Checks if the object exists in S3
    2. Validates content type (if expected_content_type is provided)
    3. Retrieves object metadata (size, content type)
    4. Computes SHA256 hash of the object
    5. Returns a LocatedAsset with all metadata

    This is idempotent - multiple calls with the same input will return the same result.
    """
    config = load_config()
    s3_helper = S3Helper(
        region=config.aws.region,
        profile_name=config.aws.profile_name,
    )

    logger.info(f"Verifying asset s3://{input_data.bucket}/{input_data.key}")

    # Check if object exists and get metadata
    metadata = s3_helper.get_object_metadata(input_data.bucket, input_data.key)
    if not metadata:
        raise ValueError(f"Object not found: s3://{input_data.bucket}/{input_data.key}")

    # Validate content type if expected
    if input_data.expected_content_type:
        if metadata['content_type'] != input_data.expected_content_type:
            raise ValueError(
                f"Content type mismatch. Expected: {input_data.expected_content_type}, "
                f"Got: {metadata['content_type']}"
            )

    # Compute SHA256 hash
    try:
        sha256 = s3_helper.compute_object_sha256(input_data.bucket, input_data.key)
    except Exception as e:
        logger.error(f"Failed to compute SHA256 for s3://{input_data.bucket}/{input_data.key}: {e}")
        raise

    result = LocatedAsset(
        bucket=input_data.bucket,
        key=input_data.key,
        content_type=metadata['content_type'],
        size_bytes=metadata['size_bytes'],
        sha256=sha256
    )

    logger.info(
        f"Successfully verified asset s3://{input_data.bucket}/{input_data.key} "
        f"(size: {result.size_bytes} bytes, sha256: {result.sha256[:16]}...)"
    )

    return result
