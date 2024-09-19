CREATE DATABASE IF NOT EXISTS slidepull_main;
USE slidepull_main;

-- User Table
CREATE TABLE user (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    premium_status BOOLEAN DEFAULT FALSE,
    member_since DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- PDF Table
CREATE TABLE pdf (
    pdf_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    url VARCHAR(255) NOT NULL,
    FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE CASCADE
);

-- Image Table
CREATE TABLE image (
    image_id INT AUTO_INCREMENT PRIMARY KEY,
    pdf_id INT,
    url VARCHAR(255) NOT NULL,
    uploaded_on DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pdf_id) REFERENCES pdf(pdf_id) ON DELETE CASCADE
);

-- Set Table
CREATE TABLE `set` (
    set_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255),
    qrcode_url VARCHAR(255) NOT NULL,
    user_id INT,
    FOREIGN KEY (user_id) REFERENCES user(user_id) ON DELETE CASCADE
);

-- Images_per_set Table (Join Table)
CREATE TABLE images_per_set (
    set_id INT,
    image_id INT,
    PRIMARY KEY (set_id, image_id),
    FOREIGN KEY (set_id) REFERENCES `set`(set_id) ON DELETE CASCADE,
    FOREIGN KEY (image_id) REFERENCES image(image_id) ON DELETE CASCADE
);
