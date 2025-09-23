import pytest
from unittest.mock import AsyncMock, patch
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from worker.workflows.image_processing import ImageProcessingWorkflow
from worker.models import WorkflowInput, LocatedAsset, OcrResult, PersistResult


@pytest.fixture
async def workflow_environment():
    """Create a test workflow environment."""
    async with WorkflowEnvironment() as env:
        yield env


@pytest.fixture
def sample_workflow_input():
    """Sample workflow input for testing."""
    return WorkflowInput(
        job_id="test-job-123",
        bucket="test-bucket",
        key="test-image.jpg",
        expected_content_type="image/jpeg"
    )


@pytest.fixture
def mock_located_asset():
    """Mock located asset response."""
    return LocatedAsset(
        bucket="test-bucket",
        key="test-image.jpg",
        content_type="image/jpeg",
        size_bytes=1024000,
        sha256="abcd1234567890abcd1234567890abcd1234567890abcd1234567890abcd1234"
    )


@pytest.fixture
def mock_ocr_result():
    """Mock OCR result response."""
    return OcrResult(
        ocr_engine="textract",
        ocr_version="2023.01.01",
        s3_ocr_key="artifacts/test-job-123/textract.json",
        page_count=1
    )


@pytest.fixture
def mock_persist_result():
    """Mock persist result response."""
    return PersistResult(
        recipe_id="test-job-123",
        manifest_s3_key="artifacts/test-job-123/manifest.json"
    )


class TestImageProcessingWorkflow:
    """Test cases for the ImageProcessingWorkflow."""

    async def test_workflow_success_path(
        self,
        workflow_environment: WorkflowEnvironment,
        sample_workflow_input: WorkflowInput,
        mock_located_asset: LocatedAsset,
        mock_ocr_result: OcrResult,
        mock_persist_result: PersistResult
    ):
        """Test the successful execution path of the workflow."""

        # Mock the activities
        async def mock_verify_and_locate_asset(input_data):
            return mock_located_asset

        async def mock_ocr_textract(input_data):
            return mock_ocr_result

        async def mock_persist_artifacts(input_data):
            return mock_persist_result

        # Create worker with mocked activities
        worker = Worker(
            workflow_environment.client,
            task_queue="test-queue",
            workflows=[ImageProcessingWorkflow],
            activities=[
                mock_verify_and_locate_asset,
                mock_ocr_textract,
                mock_persist_artifacts
            ]
        )

        async with worker:
            # Execute workflow
            result = await workflow_environment.client.execute_workflow(
                ImageProcessingWorkflow.run,
                sample_workflow_input,
                id="test-workflow-123",
                task_queue="test-queue"
            )

            # Assertions
            assert result.job_id == "test-job-123"
            assert result.status == "succeeded"
            assert result.recipe_id == "test-job-123"
            assert result.s3_raw_key == "test-image.jpg"
            assert result.sha256 == mock_located_asset.sha256
            assert result.ocr_s3_key == "artifacts/test-job-123/textract.json"
            assert result.manifest_s3_key == "artifacts/test-job-123/manifest.json"
            assert result.page_count == 1


    async def test_workflow_with_activity_failure(
        self,
        workflow_environment: WorkflowEnvironment,
        sample_workflow_input: WorkflowInput
    ):
        """Test workflow behavior when an activity fails."""

        async def mock_verify_and_locate_asset_failure(input_data):
            raise ValueError("S3 object not found")

        # Create worker with failing activity
        worker = Worker(
            workflow_environment.client,
            task_queue="test-queue",
            workflows=[ImageProcessingWorkflow],
            activities=[mock_verify_and_locate_asset_failure]
        )

        async with worker:
            # Execute workflow and expect failure
            with pytest.raises(Exception) as exc_info:
                await workflow_environment.client.execute_workflow(
                    ImageProcessingWorkflow.run,
                    sample_workflow_input,
                    id="test-workflow-failure-123",
                    task_queue="test-queue"
                )

            # Check that the failure is propagated
            assert "S3 object not found" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__])