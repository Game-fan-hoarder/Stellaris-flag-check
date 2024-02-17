CREATE TABLE IF NOT EXISTS tags (
    tag_id VARCHAR(255) PRIMARY KEY,
    parent_tag_id VARCHAR(255),
    target VARCHAR(255) UNIQUE,
    display VARCHAR(255),
    FOREIGN KEY (parent_tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS saves (
    save_id VARCHAR(255) PRIMARY KEY,
    save_location VARCHAR(255) UNIQUE
);

CREATE TABLE IF NOT EXISTS saves_tags (
    tag_id VARCHAR(255),
    save_id VARCHAR(255),
    PRIMARY KEY (tag_id, save_id),
    FOREIGN KEY (tag_id) REFERENCES tags(tag_id),
    FOREIGN KEY (save_id) REFERENCES saves(save_id)
);
