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
    region: str = "us-east-1"
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
    region: str = "us-east-1"
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None


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
            region=os.getenv("S3_REGION", "us-east-1"),
            bucket=os.getenv("S3_BUCKET", "photo-worker-bucket")
        ),
        database=DatabaseConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "photo_worker"),
            username=os.getenv("DB_USERNAME", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
            pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20"))
        ),
        aws=AWSConfig(
            region=os.getenv("AWS_REGION", "us-east-1"),
            access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO")
    )