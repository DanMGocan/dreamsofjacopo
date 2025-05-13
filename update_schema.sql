-- This script adds the set_image table to link sets with their images in order

USE slidepull_main;

-- Create the set_image table if it doesn't exist already
CREATE TABLE IF NOT EXISTS set_image (
    set_image_id INT AUTO_INCREMENT PRIMARY KEY,
    set_id INT NOT NULL,
    image_id INT NOT NULL,
    display_order INT NOT NULL,  -- Order of images in the set
    FOREIGN KEY (set_id) REFERENCES `set`(set_id) ON DELETE CASCADE,
    FOREIGN KEY (image_id) REFERENCES image(image_id) ON DELETE CASCADE,
    UNIQUE KEY unique_set_image (set_id, image_id)  -- Prevent duplicate image in a set
);

-- Add an index for faster queries
CREATE INDEX idx_set_id ON set_image(set_id);

-- Add a trigger to update slide_count in sets when images are added/removed
DELIMITER //
CREATE TRIGGER IF NOT EXISTS update_set_slide_count_after_insert
AFTER INSERT ON set_image
FOR EACH ROW
BEGIN
    UPDATE `set` SET slide_count = (
        SELECT COUNT(*) FROM set_image WHERE set_id = NEW.set_id
    ) WHERE set_id = NEW.set_id;
END//

CREATE TRIGGER IF NOT EXISTS update_set_slide_count_after_delete
AFTER DELETE ON set_image
FOR EACH ROW
BEGIN
    UPDATE `set` SET slide_count = (
        SELECT COUNT(*) FROM set_image WHERE set_id = OLD.set_id
    ) WHERE set_id = OLD.set_id;
END//
DELIMITER ;

-- Notify that the update completed
SELECT 'Set-image relationship table added successfully' AS Message;
