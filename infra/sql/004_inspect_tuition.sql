-- SSMS: 127.0.0.1,14330. Read-only inspection of the local tuition database.
USE tuition_db;
GO

-- id is an internal relational key; mssv is the student code used on the Web.
SELECT id AS student_id, mssv, full_name
FROM dbo.students
ORDER BY id ASC;

-- invoice_id identifies a bill; student_id links it to the student above.
SELECT i.id AS invoice_id, i.student_id, s.mssv, s.full_name,
       i.semester, i.amount_due, i.status, i.paid_payment_id
FROM dbo.tuition_invoices AS i
JOIN dbo.students AS s ON s.id = i.student_id
ORDER BY i.id ASC;

-- Expected: 0 rows. Every payment item must refer to the correct student's bill.
SELECT p.payment_id, p.mssv, pi.invoice_id
FROM payment_db.dbo.payment_items AS pi
JOIN payment_db.dbo.payments AS p ON p.payment_id = pi.payment_id
LEFT JOIN dbo.tuition_invoices AS i ON i.id = pi.invoice_id
LEFT JOIN dbo.students AS s ON s.id = i.student_id
WHERE i.id IS NULL OR s.mssv <> p.mssv OR i.amount_due <> pi.amount;
