-- SSMS: 127.0.0.1,14330. Read-only checks before/after the Web demo.
-- Use independent browser sessions for huy and huy2.
DECLARE @mssv VARCHAR(24) = 'SV20261001';

SELECT u.username, u.email, u.email_verified_at,
       a.account_number, a.balance, a.status
FROM account_db.dbo.users AS u
JOIN account_db.dbo.accounts AS a ON a.user_id = u.id
WHERE u.username IN ('huy', 'huy2')
ORDER BY u.username;

SELECT s.mssv, s.full_name, i.id AS invoice_id,
       i.semester, i.amount_due, i.status, i.paid_payment_id
FROM tuition_db.dbo.students AS s
JOIN tuition_db.dbo.tuition_invoices AS i ON i.student_id = s.id
WHERE s.mssv = @mssv
ORDER BY i.id;

SELECT u.username, p.payment_id, p.mssv, p.payer_email,
       p.total_amount, p.status, p.phase, p.error_message
FROM payment_db.dbo.payments AS p
JOIN account_db.dbo.users AS u ON u.id = p.payer_user_id
WHERE p.mssv = @mssv AND u.username IN ('huy', 'huy2')
ORDER BY p.created_at, p.payment_id;

-- For this fresh unpaid tuition group, expect exactly one successful DEBIT.
SELECT u.username, e.payment_id, e.entry_type, e.amount
FROM account_db.dbo.account_entries AS e
JOIN account_db.dbo.accounts AS a ON a.id = e.account_id
JOIN account_db.dbo.users AS u ON u.id = a.user_id
JOIN payment_db.dbo.payments AS p ON p.payment_id = e.payment_id
WHERE p.mssv = @mssv AND u.username IN ('huy', 'huy2')
ORDER BY e.id;
