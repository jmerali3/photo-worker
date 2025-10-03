import os
from typing import Optional
from pydantic import BaseModel


class TemporalConfig(BaseModel):
    target: str = "localhost:7233"
    namespace: str = "default"
    task_queue: str = "recipe-process"
    max_concurrent_activities: int = 10
    max_concurrent_workflow_tasks: int = 5


class S3Config(BaseModel):
    region: str = "us-west-2"
    bucket: str


class DatabaseConfig(BaseModel):
    host: str = "localhost"
    port: int = 5432
    database: str = "photo_worker"
    username: str
    password: str
    pool_size: int = 10
    max_overflow: int = 20

    @property
    def connection_string(self) -> str:
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


class AWSConfig(BaseModel):
    region: str = "us-west-2"
    profile_name: Optional[str] = None


class Config(BaseModel):
    temporal: TemporalConfig
    s3: S3Config
    database: DatabaseConfig
    aws: AWSConfig
    log_level: str = "INFO"


def load_config() -> Config:
    return Config(
        temporal=TemporalConfig(
            target=os.getenv("TEMPORAL_TARGET", "localhost:7233"),
            namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
            task_queue=os.getenv("TEMPORAL_TASK_QUEUE", "recipe-process"),
            max_concurrent_activities=int(os.getenv("MAX_ACTIVITIES", "10")),
            max_concurrent_workflow_tasks=int(os.getenv("MAX_WF_TASKS", "5"))
        ),
        s3=S3Config(
            region=os.getenv("S3_REGION", "us-west-2"),
            bucket=os.getenv("S3_BUCKET", "my-ocr-processed-bucket-070703032025")
        ),
        database=DatabaseConfig(
            host=os.getenv(
                "DB_HOST", "photo-dev-dev-pg.cr8uowes62h6.us-west-2.rds.amazonaws.com"
            ),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "photo_worker"),
            username=os.getenv("DB_USERNAME", "appuser"),
            password=os.getenv("DB_PASSWORD", None),
            pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20"))
        ),
        aws=AWSConfig(
            region=os.getenv("AWS_REGION", "us-west-2"),
            profile_name=(
                os.getenv("AWS_PROFILE")
                or os.getenv("AWS_DEFAULT_PROFILE")
                or os.getenv("AWS_PROFILE_NAME")
            )
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO")
    )
