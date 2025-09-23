import logging
from datetime import timedelta
from temporalio import workflow

from worker.models import (
    WorkflowInput, WorkflowResult, LocateAssetInput, OcrInput, PersistInput
)
from worker.activities.io_s3 import verify_and_locate_asset
from worker.activities.ocr_textract import ocr_textract
from worker.activities.persist import persist_artifacts

logger = logging.getLogger(__name__)


@workflow.defn
class ImageProcessingWorkflow:
    """
    Main workflow for processing recipe images end-to-end.

    This workflow orchestrates the complete pipeline:
    1. Verify and locate the asset in S3
    2. Run OCR using AWS Textract
    3. Persist artifacts and metadata

    The workflow is designed to be:
    - Idempotent: Can be safely retried
    - Durable: Temporal handles retries and failures
    - Observable: Each step is tracked independently
    """

    @workflow.run
    async def run(self, input_data: WorkflowInput) -> WorkflowResult:
        """Execute the image processing workflow."""
        workflow.logger.info(f"Starting image processing workflow for job {input_data.job_id}")

        # Step 1: Verify and locate asset in S3
        workflow.logger.info("Step 1: Verifying asset in S3")
        locate_input = LocateAssetInput(
            bucket=input_data.bucket,
            key=input_data.key,
            expected_content_type=input_data.expected_content_type
        )

        located_asset = await workflow.execute_activity(
            verify_and_locate_asset,
            locate_input,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=workflow.RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=30),
                maximum_attempts=5,
                backoff_coefficient=2.0
            )
        )

        workflow.logger.info(
            f"Asset verified: {located_asset.size_bytes} bytes, "
            f"SHA256: {located_asset.sha256[:16]}..."
        )

        # Step 2: Run OCR using Textract
        workflow.logger.info("Step 2: Running OCR with Textract")
        ocr_input = OcrInput(
            bucket=located_asset.bucket,
            key=located_asset.key,
            engine="textract"
        )

        ocr_result = await workflow.execute_activity(
            ocr_textract,
            ocr_input,
            start_to_close_timeout=timedelta(minutes=5),  # Textract can take a while
            retry_policy=workflow.RetryPolicy(
                initial_interval=timedelta(seconds=2),
                maximum_interval=timedelta(seconds=60),
                maximum_attempts=3,
                backoff_coefficient=2.0
            )
        )

        workflow.logger.info(
            f"OCR completed: {ocr_result.page_count} pages, "
            f"version: {ocr_result.ocr_version}"
        )

        # Step 3: Persist artifacts and metadata
        workflow.logger.info("Step 3: Persisting artifacts and metadata")
        persist_input = PersistInput(
            job_id=input_data.job_id,
            s3_raw_key=located_asset.key,
            sha256=located_asset.sha256,
            ocr_s3_key=ocr_result.s3_ocr_key,
            ocr_engine=ocr_result.ocr_engine,
            ocr_version=ocr_result.ocr_version,
            page_count=ocr_result.page_count
        )

        persist_result = await workflow.execute_activity(
            persist_artifacts,
            persist_input,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=workflow.RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
                backoff_coefficient=2.0
            )
        )

        # Create final workflow result
        workflow_result = WorkflowResult(
            job_id=input_data.job_id,
            status="succeeded",
            recipe_id=persist_result.recipe_id,
            s3_raw_key=located_asset.key,
            sha256=located_asset.sha256,
            ocr_s3_key=ocr_result.s3_ocr_key,
            manifest_s3_key=persist_result.manifest_s3_key,
            page_count=ocr_result.page_count,
            created_at=workflow.utcnow()
        )

        workflow.logger.info(
            f"Image processing workflow completed successfully for job {input_data.job_id}. "
            f"Manifest: {persist_result.manifest_s3_key}"
        )

        return workflow_result