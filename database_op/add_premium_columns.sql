-- Add columns for premium features to the user table
ALTER TABLE user
ADD COLUMN additional_presentations INT DEFAULT 0,
ADD COLUMN additional_storage_days INT DEFAULT 0,
ADD COLUMN additional_sets INT DEFAULT 0;

-- Add an index for faster queries on premium_status
CREATE INDEX idx_premium_status ON user(premium_status);
