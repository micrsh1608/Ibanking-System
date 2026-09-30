# REST API Design - TV2

Base URL:

```text
http://localhost:8002
```

## 1. GET /api/v1/tuition/{mssv}

### Request

```http
GET /api/v1/tuition/52200001
```

### 200

```json
{
  "mssv": "52200001",
  "full_name": "Nguyen Van An",
  "email": "an@gmail.com",
  "amount": "12500000.00",
  "status": "UNPAID",
  "paid_at": null,
  "paid_transaction_id": null
}
```

### 404

```json
{
  "detail": "Student or tuition not found"
}
```

---

## 2. POST /api/v1/otp/send

### Request

```json
{
  "transaction_id": "TX001",
  "mssv": "52200001",
  "email": "an@gmail.com"
}
```

### 200

```json
{
  "transaction_id": "TX001",
  "message": "OTP sent successfully",
  "expires_in": 300
}
```

---

## 3. POST /api/v1/otp/verify

### Request

```json
{
  "transaction_id": "TX001",
  "otp": "583921"
}
```

### 200

```json
{
  "transaction_id": "TX001",
  "verified": true,
  "message": "OTP verified successfully"
}
```

### Error

- 400 Invalid OTP
- 400 OTP expired
- 400 OTP not found or already used
- 409 OTP already used by another concurrent request

---

## 4. PATCH /api/v1/internal/tuition/{mssv}/paid

### Request

```json
{
  "transaction_id": "TX001"
}
```

### 200

```json
{
  "mssv": "52200001",
  "full_name": "Nguyen Van An",
  "email": "an@gmail.com",
  "amount": "12500000.00",
  "status": "PAID",
  "paid_transaction_id": "TX001"
}
```

### 409

```json
{
  "detail": "Tuition has already been paid"
}
```
