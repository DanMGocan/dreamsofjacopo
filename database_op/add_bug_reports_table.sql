-- Create the bug_reports table
CREATE TABLE IF NOT EXISTS bug_reports (
    report_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    bug_description TEXT NOT NULL,
    status TINYINT NOT NULL DEFAULT 1, -- 0: resolved, 1: investigating, 2: resolved, 3: not_a_bug
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE CASCADE
);

-- Create an index on user_id for faster lookups
CREATE INDEX idx_bug_reports_user_id ON bug_reports(user_id);

-- Create an index on status for filtering
CREATE INDEX idx_bug_reports_status ON bug_reports(status);
