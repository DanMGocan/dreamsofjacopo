-- SlidePull Database Schema
-- This schema creates the necessary tables and indexes for the SlidePull application
-- All business logic is handled in server-side Python code

CREATE DATABASE IF NOT EXISTS slidepull_main;
USE slidepull_main;

-- User Table - Stores user account information
CREATE TABLE IF NOT EXISTS user (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    premium_status INT DEFAULT 0,
    member_since DATETIME DEFAULT CURRENT_TIMESTAMP,
    account_activated BOOLEAN DEFAULT FALSE,
    login_method ENUM("slide_pull", "google", "microsoft") NOT NULL,
    alias VARCHAR(255) NOT NULL UNIQUE
);

-- PDF Table - Stores information about uploaded PDF files
CREATE TABLE IF NOT EXISTS pdf (
    pdf_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    url VARCHAR(512) NOT NULL,
    original_filename VARCHAR(255),
    sas_token VARCHAR(2048) NOT NULL,
    sas_token_expiry DATETIME,
    num_slides INT DEFAULT 0,
    file_size_kb INT DEFAULT 0,
    download_count INT DEFAULT 0,
    pdf_qrcode_url VARCHAR(512),
    pdf_qrcode_sas_token VARCHAR(2048),
    pdf_qrcode_sas_token_expiry DATETIME,
    unique_code VARCHAR(36) UNIQUE NOT NULL,
    FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE CASCADE
);

-- Image Table - Stores information about extracted slide images
CREATE TABLE IF NOT EXISTS image (
    image_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    pdf_id INT NOT NULL,
    url VARCHAR(512) NOT NULL,
    uploaded_on DATETIME DEFAULT CURRENT_TIMESTAMP,
    sas_token VARCHAR(2048) NOT NULL,
    sas_token_expiry DATETIME,
    FOREIGN KEY (pdf_id) REFERENCES pdf(pdf_id) ON DELETE CASCADE
);

-- Thumbnail Table - Stores information about image thumbnails
CREATE TABLE IF NOT EXISTS thumbnail (
    thumbnail_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    image_id INT NOT NULL,
    pdf_id INT NOT NULL,
    url VARCHAR(512) NOT NULL,
    sas_token VARCHAR(2048) NOT NULL,
    sas_token_expiry DATETIME NOT NULL,
    FOREIGN KEY (pdf_id) REFERENCES pdf(pdf_id) ON DELETE CASCADE,
    FOREIGN KEY (image_id) REFERENCES image(image_id) ON DELETE CASCADE
);

-- Set Table - Stores information about slide sets created by users
CREATE TABLE IF NOT EXISTS `set` (
    set_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    pdf_id INT NOT NULL,
    name VARCHAR(255),
    user_id INT NOT NULL,
    url VARCHAR(512),
    sas_token VARCHAR(2048) NOT NULL,
    sas_token_expiry DATETIME NOT NULL,
    qrcode_url VARCHAR(512),
    qrcode_sas_token VARCHAR(2048),
    qrcode_sas_token_expiry DATETIME,
    download_count INT DEFAULT 0,
    slide_count INT DEFAULT 0,
    unique_code VARCHAR(36) UNIQUE NOT NULL,
    FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE CASCADE,
    FOREIGN KEY (pdf_id) REFERENCES pdf(pdf_id) ON DELETE CASCADE
);

-- Set-Image relationship table - Links sets with their images
CREATE TABLE IF NOT EXISTS set_image (
    set_image_id INT AUTO_INCREMENT PRIMARY KEY,
    set_id INT NOT NULL,
    image_id INT NOT NULL,
    display_order INT NOT NULL,  -- Order of images in the set
    FOREIGN KEY (set_id) REFERENCES `set`(set_id) ON DELETE CASCADE,
    FOREIGN KEY (image_id) REFERENCES image(image_id) ON DELETE CASCADE,
    UNIQUE KEY unique_set_image (set_id, image_id)  -- Prevent duplicate image in a set
);

-- Bug Reports Table - Stores user-submitted bug reports
CREATE TABLE IF NOT EXISTS bug_reports (
    report_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    bug_description TEXT NOT NULL,
    status TINYINT NOT NULL DEFAULT 1, -- 0: closed, 1: investigating, 2: in progress, 3: not_a_bug
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE CASCADE
);

-- Create indexes for performance optimization
CREATE INDEX idx_user_id ON pdf(user_id);
CREATE INDEX idx_pdf_id ON image(pdf_id);
CREATE INDEX idx_bug_reports_user_id ON bug_reports(user_id);
CREATE INDEX idx_bug_reports_status ON bug_reports(status);
CREATE INDEX idx_set_id ON set_image(set_id);
CREATE INDEX idx_pdf_unique_code ON pdf(unique_code);
CREATE INDEX idx_set_unique_code ON `set`(unique_code);
CREATE INDEX idx_image_id_thumbnail ON thumbnail(image_id);
CREATE INDEX idx_user_id_set ON `set`(user_id);
