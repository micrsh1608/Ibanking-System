CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mssv VARCHAR(30) NOT NULL UNIQUE,
    full_name VARCHAR(150) NOT NULL,
    phone VARCHAR(30),
    email VARCHAR(255) NOT NULL
);

CREATE TABLE tuitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL UNIQUE,
    amount DECIMAL(15,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'UNPAID',
    paid_at DATETIME NULL,
    paid_transaction_id VARCHAR(100) NULL,
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE TABLE otps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id VARCHAR(100) NOT NULL,
    mssv VARCHAR(30) NOT NULL,
    email VARCHAR(255) NOT NULL,
    otp_code VARCHAR(20) NOT NULL,
    expires_at DATETIME NOT NULL,
    used BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL
);

CREATE INDEX ix_students_mssv ON students(mssv);
CREATE INDEX ix_tuitions_student_id ON tuitions(student_id);
CREATE INDEX ix_otps_transaction_id ON otps(transaction_id);
CREATE INDEX ix_otps_expires_at ON otps(expires_at);
