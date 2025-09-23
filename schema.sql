-- Photo Worker Database Schema
-- Single-tenant recipe image processing system

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- recipes: one per uploaded/processed image
CREATE TABLE IF NOT EXISTS recipes (
  id UUID PRIMARY KEY,
  s3_raw_key TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',     -- queued|running|succeeded|failed
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- OCR pointer and summary
CREATE TABLE IF NOT EXISTS recipe_ocr (
  recipe_id UUID PRIMARY KEY REFERENCES recipes(id) ON DELETE CASCADE,
  s3_ocr_key TEXT NOT NULL,
  ocr_engine TEXT NOT NULL,                  -- 'textract'
  ocr_version TEXT NOT NULL,                 -- SDK/api version/date
  page_count INT DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Tagging (future): multiple versions per recipe
CREATE TABLE IF NOT EXISTS recipe_tags (
  recipe_id UUID REFERENCES recipes(id) ON DELETE CASCADE,
  schema_version INT NOT NULL,
  s3_tags_key TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (recipe_id, schema_version)
);

-- Indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_recipes_sha ON recipes(content_sha256);
CREATE INDEX IF NOT EXISTS idx_recipes_status ON recipes(status);
CREATE INDEX IF NOT EXISTS idx_recipes_created_at ON recipes(created_at);
CREATE INDEX IF NOT EXISTS idx_recipe_ocr_created_at ON recipe_ocr(created_at);
CREATE INDEX IF NOT EXISTS idx_recipe_tags_schema_version ON recipe_tags(schema_version);

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to automatically update updated_at on recipes table
DROP TRIGGER IF EXISTS update_recipes_updated_at ON recipes;
CREATE TRIGGER update_recipes_updated_at
    BEFORE UPDATE ON recipes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Sample data for development/testing (optional)
-- Uncomment these lines if you want sample data

-- INSERT INTO recipes (id, s3_raw_key, content_sha256, status) VALUES
--   (uuid_generate_v4(), 'raw/sample-recipe-1.jpg', 'abc123def456...', 'succeeded'),
--   (uuid_generate_v4(), 'raw/sample-recipe-2.png', 'def456ghi789...', 'succeeded')
-- ON CONFLICT (id) DO NOTHING;

-- View for easy querying of complete recipe information
CREATE OR REPLACE VIEW recipe_full_info AS
SELECT
    r.id,
    r.s3_raw_key,
    r.content_sha256,
    r.status,
    r.created_at,
    r.updated_at,
    ro.s3_ocr_key,
    ro.ocr_engine,
    ro.ocr_version,
    ro.page_count,
    ro.created_at as ocr_created_at
FROM recipes r
LEFT JOIN recipe_ocr ro ON r.id = ro.recipe_id;

-- Comment on tables and columns for documentation
COMMENT ON TABLE recipes IS 'Main table storing information about uploaded recipe images';
COMMENT ON COLUMN recipes.id IS 'Primary key, used as job_id in Temporal workflows';
COMMENT ON COLUMN recipes.s3_raw_key IS 'S3 key of the original uploaded image';
COMMENT ON COLUMN recipes.content_sha256 IS 'SHA256 hash of the original image content';
COMMENT ON COLUMN recipes.status IS 'Processing status: queued, running, succeeded, failed';

COMMENT ON TABLE recipe_ocr IS 'OCR processing results and metadata';
COMMENT ON COLUMN recipe_ocr.s3_ocr_key IS 'S3 key where full OCR JSON is stored';
COMMENT ON COLUMN recipe_ocr.ocr_engine IS 'OCR engine used (currently only textract)';
COMMENT ON COLUMN recipe_ocr.ocr_version IS 'Version/date of the OCR engine/API';

COMMENT ON TABLE recipe_tags IS 'LLM-generated tags (future feature, multiple schema versions supported)';
COMMENT ON COLUMN recipe_tags.schema_version IS 'Version of the tagging schema used';
COMMENT ON COLUMN recipe_tags.s3_tags_key IS 'S3 key where tags JSON is stored';