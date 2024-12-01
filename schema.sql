CREATE DATABASE IF NOT EXISTS slidepull_main;
USE slidepull_main;

-- User Table
CREATE TABLE user (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    premium_status INT DEFAULT 0,
    member_since DATETIME DEFAULT CURRENT_TIMESTAMP,
    account_activated BOOLEAN DEFAULT FALSE,
    login_method ENUM("slide_pull", "google", "microsoft") NOT NULL,
    alias VARCHAR(255) NOT NULL UNIQUE
);

-- PDF Table
CREATE TABLE pdf (
    pdf_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    url VARCHAR(512) NOT NULL,  -- Reduced length for URL
    original_filename VARCHAR(255),
    sas_token VARCHAR(256) NOT NULL,
    sas_token_expiry DATETIME,
    FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE CASCADE
);

-- Image Table
CREATE TABLE image (
    image_id INT AUTO_INCREMENT PRIMARY KEY,
    pdf_id INT,
    url VARCHAR(512) NOT NULL,  -- Reduced length for URL
    uploaded_on DATETIME DEFAULT CURRENT_TIMESTAMP,
    sas_token VARCHAR(256) NOT NULL,
    sas_token_expiry DATETIME,
    FOREIGN KEY (pdf_id) REFERENCES pdf(pdf_id) ON DELETE CASCADE
);

-- Thumbnail Table
CREATE TABLE thumbnail (
    thumbnail_id INT AUTO_INCREMENT PRIMARY KEY,
    image_id INT NOT NULL,
    pdf_id INT NOT NULL,
    url VARCHAR(255) NOT NULL,
    sas_token VARCHAR(2048) NOT NULL,
    sas_token_expiry DATETIME NOT NULL,
    FOREIGN KEY (pdf_id) REFERENCES pdf(pdf_id) ON DELETE CASCADE,
    FOREIGN KEY (image_id) REFERENCES image(image_id) ON DELETE CASCADE
);

-- Set Table
CREATE TABLE `set` (
    set_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255),
    user_id INT,
    sas_token VARCHAR(2048) NOT NULL,
    sas_token_expiry DATETIME NOT NULL,
    qrcode_url VARCHAR(512),  -- Reduced length for QR code URL
    qrcode_sas_token VARCHAR(2048), -- SAS token for QR code
    qrcode_sas_token_expiry DATETIME, -- Expiry of the QR code SAS token
    FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE CASCADE
);

-- Images_per_set Table (Join Table)
CREATE TABLE set_images (
    set_id INT,
    image_id INT,
    PRIMARY KEY (set_id, image_id),
    FOREIGN KEY (set_id) REFERENCES `set`(set_id) ON DELETE CASCADE,
    FOREIGN KEY (image_id) REFERENCES image(image_id) ON DELETE CASCADE
);

-- Add indexes for faster query performance on critical fields
CREATE INDEX idx_user_id ON pdf(user_id);
CREATE INDEX idx_pdf_id ON image(pdf_id);
CREATE INDEX idx_set_id ON set_images(set_id);
CREATE INDEX idx_image_id ON set_images(image_id);
