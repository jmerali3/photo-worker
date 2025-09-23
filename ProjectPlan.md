# Photo Worker Implementation Plan

## Project Overview
Implementing a Temporal worker service (photo-worker) that processes uploaded recipe images end-to-end using Temporal, S3, Textract, and Postgres.

## Implementation Tasks

### Phase 1: Project Foundation
- [x] Create project structure and configuration files
- [ ] Implement configuration module (config.py)
- [ ] Create utility modules (hashing, s3, db helpers)
- [ ] Implement activity contracts and data models

### Phase 2: Core Activities
- [ ] Implement S3 verification activity (io_s3.py)
- [ ] Implement Textract OCR activity (ocr_textract.py)
- [ ] Implement persistence activity (persist.py)

### Phase 3: Workflow & Runner
- [ ] Implement main workflow orchestration (image_processing.py)
- [ ] Implement worker runner (run_worker.py)

### Phase 4: Configuration & Testing
- [ ] Create requirements.txt with dependencies
- [ ] Create .env.example and .env templates
- [ ] Create basic test files
- [ ] Create SQL schema file

## Architecture Notes
- Single-tenant design (no per-tenant isolation needed)
- Task queue: `recipe-process`
- Artifacts (large JSON) → S3, Metadata → Postgres
- Idempotent activities with proper retry policies
- Future tagging capability without re-running OCR

## Key Components
1. **Verify**: S3 asset verification (exists, content-type, size, checksum)
2. **OCR**: AWS Textract text extraction (sync API for MVP)
3. **Persist**: Store OCR JSON in S3 + metadata in Postgres
4. **Orchestrate**: Temporal workflow managing the pipeline
5. **Future**: LLM tagging workflow (skeleton implementation)