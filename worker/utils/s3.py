import json
import logging
from io import BytesIO
from typing import Dict, Any, Optional

from botocore.exceptions import ClientError, NoCredentialsError

from worker.utils.aws import create_boto3_session
from worker.utils.hashing import compute_sha256_from_stream

logger = logging.getLogger(__name__)


class S3Helper:
    def __init__(
        self,
        region: str = "us-west-2",
        profile_name: Optional[str] = None,
    ):
        session = create_boto3_session(
            region=region,
            profile_name=profile_name,
        )
        self.s3_client = session.client('s3')
        self.region = region

    def get_object_metadata(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        """Get object metadata without downloading the content."""
        try:
            response = self.s3_client.head_object(Bucket=bucket, Key=key)
            return {
                'content_type': response.get('ContentType', ''),
                'size_bytes': response.get('ContentLength', 0),
                'last_modified': response.get('LastModified'),
                'etag': response.get('ETag', '').strip('"'),
                'metadata': response.get('Metadata', {})
            }
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.warning(f"Object not found: s3://{bucket}/{key}")
                return None
            logger.error(f"Error getting object metadata: {e}")
            raise
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            raise

    def download_object_stream(self, bucket: str, key: str) -> BytesIO:
        """Download object and return as BytesIO stream."""
        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            stream = BytesIO(response['Body'].read())
            stream.seek(0)
            return stream
        except ClientError as e:
            logger.error(f"Error downloading object s3://{bucket}/{key}: {e}")
            raise
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            raise

    def compute_object_sha256(self, bucket: str, key: str) -> str:
        """Download object and compute SHA256 hash."""
        stream = self.download_object_stream(bucket, key)
        return compute_sha256_from_stream(stream)

    def put_json_object(self, bucket: str, key: str, data: Dict[str, Any]) -> bool:
        """Upload JSON data to S3."""
        try:
            json_string = json.dumps(data, indent=2, default=str)
            self.s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=json_string,
                ContentType='application/json'
            )
            logger.info(f"Successfully uploaded JSON to s3://{bucket}/{key}")
            return True
        except ClientError as e:
            logger.error(f"Error uploading JSON to s3://{bucket}/{key}: {e}")
            raise
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            raise

    def get_json_object(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        """Download and parse JSON object from S3."""
        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read().decode('utf-8')
            return json.loads(content)
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.warning(f"JSON object not found: s3://{bucket}/{key}")
                return None
            logger.error(f"Error downloading JSON from s3://{bucket}/{key}: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON from s3://{bucket}/{key}: {e}")
            raise
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            raise

    def object_exists(self, bucket: str, key: str) -> bool:
        """Check if object exists in S3."""
        try:
            self.s3_client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            logger.error(f"Error checking object existence: {e}")
            raise
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            raise
