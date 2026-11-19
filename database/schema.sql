CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attendance_date TEXT NOT NULL UNIQUE,
    work_mode TEXT NOT NULL CHECK(work_mode IN ('WFH','LEAVE')),
    selected_at TEXT NOT NULL,
    email_status TEXT NOT NULL,
    email_created_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY,
    setting_key TEXT UNIQUE NOT NULL,
    setting_value TEXT NOT NULL
);
