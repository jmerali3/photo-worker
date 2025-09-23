import pytest
from unittest.mock import Mock, patch, AsyncMock
from botocore.exceptions import ClientError

from worker.models import LocateAssetInput, OcrInput, PersistInput
from worker.activities.io_s3 import verify_and_locate_asset
from worker.activities.ocr_textract import ocr_textract
from worker.activities.persist import persist_artifacts


class TestVerifyAndLocateAsset:
    """Test cases for the verify_and_locate_asset activity."""

    @patch('worker.activities.io_s3.S3Helper')
    @patch('worker.activities.io_s3.load_config')
    async def test_verify_asset_success(self, mock_load_config, mock_s3_helper_class):
        """Test successful asset verification."""
        # Setup mocks
        mock_config = Mock()
        mock_config.aws.region = "us-east-1"
        mock_config.aws.access_key_id = "test-key"
        mock_config.aws.secret_access_key = "test-secret"
        mock_load_config.return_value = mock_config

        mock_s3_helper = Mock()
        mock_s3_helper_class.return_value = mock_s3_helper

        # Mock S3 responses
        mock_s3_helper.get_object_metadata.return_value = {
            'content_type': 'image/jpeg',
            'size_bytes': 1024000
        }
        mock_s3_helper.compute_object_sha256.return_value = "abcd1234567890"

        # Test input
        input_data = LocateAssetInput(
            bucket="test-bucket",
            key="test-image.jpg",
            expected_content_type="image/jpeg"
        )

        # Execute activity
        result = await verify_and_locate_asset(input_data)

        # Assertions
        assert result.bucket == "test-bucket"
        assert result.key == "test-image.jpg"
        assert result.content_type == "image/jpeg"
        assert result.size_bytes == 1024000
        assert result.sha256 == "abcd1234567890"

        # Verify S3 helper calls
        mock_s3_helper.get_object_metadata.assert_called_once_with("test-bucket", "test-image.jpg")
        mock_s3_helper.compute_object_sha256.assert_called_once_with("test-bucket", "test-image.jpg")

    @patch('worker.activities.io_s3.S3Helper')
    @patch('worker.activities.io_s3.load_config')
    async def test_verify_asset_not_found(self, mock_load_config, mock_s3_helper_class):
        """Test asset verification when object doesn't exist."""
        # Setup mocks
        mock_config = Mock()
        mock_load_config.return_value = mock_config

        mock_s3_helper = Mock()
        mock_s3_helper_class.return_value = mock_s3_helper
        mock_s3_helper.get_object_metadata.return_value = None

        input_data = LocateAssetInput(bucket="test-bucket", key="missing.jpg")

        # Execute activity and expect failure
        with pytest.raises(ValueError, match="Object not found"):
            await verify_and_locate_asset(input_data)

    @patch('worker.activities.io_s3.S3Helper')
    @patch('worker.activities.io_s3.load_config')
    async def test_verify_asset_content_type_mismatch(self, mock_load_config, mock_s3_helper_class):
        """Test asset verification with content type mismatch."""
        # Setup mocks
        mock_config = Mock()
        mock_load_config.return_value = mock_config

        mock_s3_helper = Mock()
        mock_s3_helper_class.return_value = mock_s3_helper
        mock_s3_helper.get_object_metadata.return_value = {
            'content_type': 'text/plain',
            'size_bytes': 1024
        }

        input_data = LocateAssetInput(
            bucket="test-bucket",
            key="test.txt",
            expected_content_type="image/jpeg"
        )

        # Execute activity and expect failure
        with pytest.raises(ValueError, match="Content type mismatch"):
            await verify_and_locate_asset(input_data)


class TestOcrTextract:
    """Test cases for the ocr_textract activity."""

    @patch('worker.activities.ocr_textract.activity.info')
    @patch('worker.activities.ocr_textract.S3Helper')
    @patch('worker.activities.ocr_textract.boto3.client')
    @patch('worker.activities.ocr_textract.load_config')
    async def test_ocr_textract_success(self, mock_load_config, mock_boto3_client,
                                       mock_s3_helper_class, mock_activity_info):
        """Test successful Textract OCR processing."""
        # Setup mocks
        mock_config = Mock()
        mock_config.aws.region = "us-east-1"
        mock_config.aws.access_key_id = "test-key"
        mock_config.aws.secret_access_key = "test-secret"
        mock_config.s3.bucket = "worker-bucket"
        mock_load_config.return_value = mock_config

        # Mock activity info
        mock_info = Mock()
        mock_info.workflow_id = "test-job-123"
        mock_activity_info.return_value = mock_info

        # Mock Textract response
        mock_textract_client = Mock()
        mock_boto3_client.return_value = mock_textract_client
        mock_textract_client.detect_document_text.return_value = {
            'DetectDocumentTextModelVersion': '2023.01.01',
            'DocumentMetadata': {'Pages': 1},
            'Blocks': [
                {'BlockType': 'PAGE', 'Text': 'Sample text from image'}
            ]
        }

        # Mock S3 helper
        mock_s3_helper = Mock()
        mock_s3_helper_class.return_value = mock_s3_helper
        mock_s3_helper.put_json_object.return_value = True

        # Test input
        input_data = OcrInput(bucket="test-bucket", key="test-image.jpg")

        # Execute activity
        result = await ocr_textract(input_data)

        # Assertions
        assert result.ocr_engine == "textract"
        assert result.ocr_version == "2023.01.01"
        assert result.s3_ocr_key == "artifacts/test-job-123/textract.json"
        assert result.page_count == 1

        # Verify Textract call
        mock_textract_client.detect_document_text.assert_called_once()

    @patch('worker.activities.ocr_textract.activity.info')
    @patch('worker.activities.ocr_textract.boto3.client')
    @patch('worker.activities.ocr_textract.load_config')
    async def test_ocr_textract_invalid_document(self, mock_load_config, mock_boto3_client,
                                                mock_activity_info):
        """Test Textract OCR with invalid document."""
        # Setup mocks
        mock_config = Mock()
        mock_load_config.return_value = mock_config

        mock_info = Mock()
        mock_info.workflow_id = "test-job-123"
        mock_activity_info.return_value = mock_info

        # Mock Textract error
        mock_textract_client = Mock()
        mock_boto3_client.return_value = mock_textract_client

        error_response = {'Error': {'Code': 'UnsupportedDocumentException', 'Message': 'Unsupported format'}}
        mock_textract_client.detect_document_text.side_effect = ClientError(error_response, 'DetectDocumentText')

        input_data = OcrInput(bucket="test-bucket", key="unsupported.txt")

        # Execute activity and expect failure
        with pytest.raises(ValueError, match="Unsupported document type"):
            await ocr_textract(input_data)


class TestPersistArtifacts:
    """Test cases for the persist_artifacts activity."""

    @patch('worker.activities.persist.S3Helper')
    @patch('worker.activities.persist.DatabaseHelper')
    @patch('worker.activities.persist.load_config')
    async def test_persist_artifacts_success(self, mock_load_config, mock_db_helper_class,
                                           mock_s3_helper_class):
        """Test successful artifact persistence."""
        # Setup mocks
        mock_config = Mock()
        mock_config.database = Mock()
        mock_config.aws = Mock()
        mock_config.s3.bucket = "worker-bucket"
        mock_load_config.return_value = mock_config

        # Mock database helper
        mock_db_helper = Mock()
        mock_db_helper_class.return_value = mock_db_helper
        mock_db_helper.upsert_recipe.return_value = True
        mock_db_helper.upsert_recipe_ocr.return_value = True

        # Mock S3 helper
        mock_s3_helper = Mock()
        mock_s3_helper_class.return_value = mock_s3_helper
        mock_s3_helper.put_json_object.return_value = True

        # Test input
        input_data = PersistInput(
            job_id="test-job-123",
            s3_raw_key="raw/test-image.jpg",
            sha256="abcd1234567890",
            ocr_s3_key="artifacts/test-job-123/textract.json",
            ocr_engine="textract",
            ocr_version="2023.01.01",
            page_count=1
        )

        # Execute activity
        result = await persist_artifacts(input_data)

        # Assertions
        assert result.recipe_id == "test-job-123"
        assert result.manifest_s3_key == "artifacts/test-job-123/manifest.json"

        # Verify database calls
        mock_db_helper.upsert_recipe.assert_called_once()
        mock_db_helper.upsert_recipe_ocr.assert_called_once()

        # Verify S3 manifest upload
        mock_s3_helper.put_json_object.assert_called_once()

    @patch('worker.activities.persist.S3Helper')
    @patch('worker.activities.persist.DatabaseHelper')
    @patch('worker.activities.persist.load_config')
    async def test_persist_artifacts_db_failure(self, mock_load_config, mock_db_helper_class,
                                               mock_s3_helper_class):
        """Test persistence failure when database operation fails."""
        # Setup mocks
        mock_config = Mock()
        mock_load_config.return_value = mock_config

        # Mock database helper with failure
        mock_db_helper = Mock()
        mock_db_helper_class.return_value = mock_db_helper
        mock_db_helper.upsert_recipe.return_value = False

        input_data = PersistInput(
            job_id="test-job-123",
            s3_raw_key="raw/test-image.jpg",
            sha256="abcd1234567890",
            ocr_s3_key="artifacts/test-job-123/textract.json",
            ocr_engine="textract",
            ocr_version="2023.01.01",
            page_count=1
        )

        # Execute activity and expect failure
        with pytest.raises(RuntimeError, match="Failed to upsert recipe record"):
            await persist_artifacts(input_data)


if __name__ == "__main__":
    pytest.main([__file__])