DROP TABLE IF EXISTS user;
DROP TABLE IF EXISTS project;
DROP TABLE IF EXISTS line;

-- CREATE TABLE user (
--   id INTEGER PRIMARY KEY AUTOINCREMENT,
--   username TEXT UNIQUE NOT NULL,
--   password TEXT NOT NULL
-- );

CREATE TABLE project (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  filename TEXT NOT NULL,
  stored_filename TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'uploaded',
  length NUMERIC NOT NULL,
  -- user_id INTEGER NOT NULL,
  created NUMERIC NOT NULL DEFAULT CURRENT_TIMESTAMP
  -- FOREIGN KEY (user_id) REFERENCES user (id)
);

CREATE TABLE line (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  start NUMERIC NOT NULL,
  end NUMERIC NOT NULL,
  text TEXT NOT NULL,
  CONSTRAINT fk_project
    FOREIGN KEY (project_id) 
    REFERENCES project (id)
    ON DELETE CASCADE

);