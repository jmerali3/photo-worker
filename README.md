# Photo Worker - Temporal Recipe Image Processing Service

A Temporal worker service that processes uploaded recipe images end-to-end using AWS Textract, S3, and PostgreSQL.

## Architecture

- **Single-tenant** recipe image processing
- **Temporal workflow** orchestrating S3 → Textract → Postgres pipeline
- **Idempotent activities** with proper retry policies
- **Artifact separation**: large JSON in S3, metadata in Postgres
- **Future tagging** capability without re-running OCR

## Quick Start

### Prerequisites

1. **Temporal Server** (local development):
   ```bash
   # Install Temporal CLI
   curl -sSf https://temporal.download/cli.sh | sh

   # Start local Temporal server
   temporal server start-dev
   ```

2. **PostgreSQL** database running locally

3. **AWS credentials** configured via AWS CLI profile for S3 and Textract access

### Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Database setup**:
   ```bash
   # Create database
   createdb photo_worker_dev

   # Run schema
   psql photo_worker_dev < schema.sql
   ```

3. **Environment configuration**:
   ```bash
   cp .env.example .env.local
   # Edit .env.local with your settings
   ```

4. **Run the worker**:
   ```bash
   python -m worker.run_worker
   ```

## Configuration

Environment variables (see `.env.example`):

### Temporal
- `TEMPORAL_TARGET`: Temporal server address (default: `localhost:7233`)
- `TEMPORAL_NAMESPACE`: Temporal namespace (default: `default`)
- `TEMPORAL_TASK_QUEUE`: Task queue name (default: `recipe-process`)

### AWS
- `AWS_REGION`: AWS region for S3/Textract
- `AWS_PROFILE` (optional): AWS CLI profile to use; defaults to the CLI's active profile
- `S3_BUCKET`: S3 bucket for storing artifacts

### Database
- `DB_HOST`, `DB_PORT`, `DB_NAME`: PostgreSQL connection details
- `DB_USERNAME`, `DB_PASSWORD`: Database credentials

## Usage

### Starting a Workflow

```python
from temporalio.client import Client
from worker.models import WorkflowInput

# Connect to Temporal
client = await Client.connect("localhost:7233")

# Start workflow
workflow_input = WorkflowInput(
    job_id="recipe-123",
    bucket="my-bucket",
    key="recipes/image.jpg",
    expected_content_type="image/jpeg"
)

result = await client.execute_workflow(
    "image_processing_workflow",
    workflow_input,
    id="recipe-123",
    task_queue="recipe-process"
)
```

### Workflow Process

1. **Asset Verification**: Validates S3 object exists, checks content type, computes SHA256
2. **OCR Processing**: Runs AWS Textract, stores full JSON in S3
3. **Persistence**: Updates Postgres metadata, creates manifest in S3

### Output Artifacts

- **OCR JSON**: `s3://bucket/artifacts/{job_id}/textract.json`
- **Manifest**: `s3://bucket/artifacts/{job_id}/manifest.json`
- **Database records**: `recipes` and `recipe_ocr` tables

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_activities.py

# Run with coverage
pytest --cov=worker tests/
```

### Code Quality

```bash
# Format code
black worker/ tests/

# Lint code
flake8 worker/ tests/

# Type checking
mypy worker/
```

### Docker

```bash
# Build image
docker build -t photo-worker .

# Run container
docker run --env-file .env.local photo-worker
```

## Project Structure

```
photo-worker/
├── worker/
│   ├── __init__.py
│   ├── config.py              # Environment configuration
│   ├── models.py              # Pydantic data models
│   ├── run_worker.py          # Main worker entry point
│   ├── workflows/
│   │   ├── __init__.py
│   │   └── image_processing.py # Main workflow orchestration
│   ├── activities/
│   │   ├── __init__.py
│   │   ├── io_s3.py           # S3 asset verification
│   │   ├── ocr_textract.py    # Textract OCR processing
│   │   ├── persist.py         # Database/S3 persistence
│   │   └── tagging_llm.py     # Future LLM tagging (skeleton)
│   └── utils/
│       ├── __init__.py
│       ├── hashing.py         # SHA256 utilities
│       ├── s3.py              # S3 helper functions
│       └── db.py              # Database connection helpers
├── tests/
│   ├── test_workflow_smoke.py # Workflow integration tests
│   └── test_activities.py     # Activity unit tests
├── requirements.txt           # Python dependencies
├── schema.sql                 # PostgreSQL database schema
├── Dockerfile                 # Container definition
├── .env.example              # Environment template
├── .env.local                # Local development config
└── .env.prod                 # Production config template
```

## Database Schema

### Tables

- **recipes**: Main recipe records with processing status
- **recipe_ocr**: OCR metadata and S3 pointers
- **recipe_tags**: Future LLM tagging results (multiple schema versions)

### Views

- **recipe_full_info**: Complete recipe information with OCR details

## Future Enhancements

- **LLM Tagging**: Complete implementation in `tagging_llm.py`
- **Temporal Cloud**: Switch to managed Temporal for production
- **Monitoring**: Add metrics and observability
- **Batch Processing**: Support for multi-image recipes

## Troubleshooting

### Common Issues

1. **Temporal Connection**: Ensure Temporal server is running on `localhost:7233`
2. **AWS Permissions**: Verify S3 and Textract permissions in your AWS account
3. **Database Connection**: Check PostgreSQL is running and credentials are correct
4. **S3 Bucket**: Ensure bucket exists and worker has read/write access

### Logs

Worker logs include detailed information about each step. Set `LOG_LEVEL=DEBUG` for verbose output.

## License

This project is part of the PhotoProject suite for recipe image processing.
