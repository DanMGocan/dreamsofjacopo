-- Drop existing tables if they exist
DROP TABLE IF EXISTS posts;
DROP TABLE IF EXISTS users;

-- Create the users table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE
);

-- Insert dummy rows into the users table
INSERT INTO users (name, email) VALUES 
('John Doe', 'john.doe@example.com'),
('Jane Smith', 'jane.smith@example.com'),
('Alice Johnson', 'alice.johnson@example.com');

-- Create the posts table
CREATE TABLE IF NOT EXISTS posts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Insert dummy rows into the posts table
INSERT INTO posts (user_id, content) VALUES 
(1, 'This is John Doe''s first post'),
(2, 'Jane Smith sharing an update'),
(3, 'Alice Johnson says hello'),
(1, 'John Doe again with more content');
