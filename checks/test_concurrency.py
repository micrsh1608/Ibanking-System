import os
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import httpx
from pwdlib import PasswordHash
from sqlalchemy import select

# database.py cũng đọc file .env của project.
from app.database import SessionLocal
from app.models import Account, AccountEntry, User


BASE_URL = "http://127.0.0.1:8001"

HEADERS = {
    "X-Internal-Key": os.environ["INTERNAL_API_KEY"]
}

START_BALANCE = Decimal("10000000.00")


def create_test_account(label):
    """Tạo người dùng và tài khoản mới cho mỗi lần chạy."""
    suffix = uuid4().hex

    with SessionLocal.begin() as db:
        user = User(
            username=f"test_{suffix}",
            password_hash=PasswordHash.recommended().hash(
                uuid4().hex
            ),
            full_name=f"Tài khoản kiểm thử {label}",
            email=f"{suffix}@example.com",
            is_active=True,
        )
        db.add(user)
        db.flush()

        account = Account(
            user_id=user.id,
            account_number=f"T{suffix[:20]}",
            balance=START_BALANCE,
            status="ACTIVE",
        )
        db.add(account)
        db.flush()

        result = {
            "account_id": account.id,
            "payer_user_id": user.id,
        }

    print(
        f"Tạo tài khoản {label}: "
        f"account_id={result['account_id']}, "
        f"user_id={result['payer_user_id']}"
    )

    return result


def make_debit(account, amount):
    return {
        "payment_id": str(uuid4()),
        "account_id": account["account_id"],
        "payer_user_id": account["payer_user_id"],
        "amount": amount,
    }


def post_once(path, payload):
    with httpx.Client(
        base_url=BASE_URL,
        headers=HEADERS,
        timeout=20.0,
        trust_env=False,
    ) as client:
        return client.post(path, json=payload)


def settle_response(path, payload, response):
    """Nếu nhận 503, thử lại có giới hạn bằng đúng mã và dữ liệu."""
    for attempt in range(3):
        if response.status_code != 503:
            return response

        print(
            f"  Nhận 503: thử lại lần {attempt + 1}, "
            f"giữ nguyên payment_id={payload['payment_id']}"
        )

        time.sleep(0.5 * (attempt + 1))
        response = post_once(path, payload)

    if response.status_code == 503:
        raise RuntimeError(
            "Vẫn nhận 503 sau khi thử lại. "
            "Chưa thể kết luận bài kiểm tra đạt; "
            "hãy xem lỗi trong terminal server."
        )

    return response


def post_checked(path, payload):
    response = post_once(path, payload)
    return settle_response(path, payload, response)


def post_parallel(path, payloads):
    """Gửi nhiều request gần cùng thời điểm."""
    barrier = Barrier(len(payloads))

    def worker(payload):
        with httpx.Client(
            base_url=BASE_URL,
            headers=HEADERS,
            timeout=20.0,
            trust_env=False,
        ) as client:
            barrier.wait(timeout=10)
            return client.post(path, json=payload)

    with ThreadPoolExecutor(
        max_workers=len(payloads)
    ) as executor:
        futures = [
            executor.submit(worker, payload)
            for payload in payloads
        ]
        responses = [future.result() for future in futures]

    print(
        "  HTTP lần đầu:",
        [response.status_code for response in responses],
    )

    # Chỉ thử lại những request nhận 503.
    return [
        settle_response(path, payload, response)
        for payload, response in zip(payloads, responses)
    ]


def require_status(response, expected):
    assert response.status_code == expected, (
        f"Cần HTTP {expected}, nhận {response.status_code}: "
        f"{response.text}"
    )


def read_state(account_id):
    """Đọc trực tiếp SQL Server để đối chiếu kết quả API."""
    with SessionLocal() as db:
        account = db.get(Account, account_id)
        assert account is not None, "Không tìm thấy tài khoản thử"

        rows = db.scalars(
            select(AccountEntry)
            .where(AccountEntry.account_id == account_id)
            .order_by(AccountEntry.id)
        ).all()

        entries = [
            (row.payment_id, row.entry_type, row.amount)
            for row in rows
        ]

        return account.balance, entries


def test_duplicate_debit(account):
    print("\nTEST 1: 5 yêu cầu trừ tiền cùng mã")

    payload = make_debit(account, "2000000.00")

    responses = post_parallel(
        "/internal/accounts/debit",
        [payload.copy() for _ in range(5)],
    )

    for response in responses:
        require_status(response, 200)
        assert response.json()["status"] == "DEBITED"

    balance, entries = read_state(account["account_id"])

    assert balance == Decimal("8000000.00"), (
        f"Số dư sai: {balance}"
    )
    assert entries == [
        (
            payload["payment_id"],
            "DEBIT",
            Decimal("2000000.00"),
        )
    ], f"Lịch sử không đúng: {entries}"

    print("PASS: chỉ trừ 2 triệu, chỉ có một bản ghi DEBIT")
    return payload


def test_changed_payload(account, original):
    print("\nTEST 2: Cùng mã nhưng khác số tiền")

    changed = {
        **original,
        "amount": "3000000.00",
    }

    response = post_checked(
        "/internal/accounts/debit",
        changed,
    )
    require_status(response, 409)

    balance, entries = read_state(account["account_id"])

    assert balance == Decimal("8000000.00")
    assert entries == [
        (
            original["payment_id"],
            "DEBIT",
            Decimal("2000000.00"),
        )
    ]

    print("PASS: từ chối dữ liệu khác, số dư không đổi")


def test_duplicate_refund(account, original):
    print("\nTEST 3: 5 yêu cầu hoàn tiền cùng mã")

    payload = {"payment_id": original["payment_id"]}

    responses = post_parallel(
        "/internal/accounts/refund",
        [payload.copy() for _ in range(5)],
    )

    for response in responses:
        require_status(response, 200)
        assert response.json()["status"] == "REFUNDED"

    balance, entries = read_state(account["account_id"])

    expected_entries = [
        (
            original["payment_id"],
            "DEBIT",
            Decimal("2000000.00"),
        ),
        (
            original["payment_id"],
            "REFUND",
            Decimal("2000000.00"),
        ),
    ]

    assert balance == START_BALANCE, f"Số dư sai: {balance}"
    assert entries == expected_entries, (
        f"Lịch sử không đúng: {entries}"
    )

    # Gửi lại yêu cầu trừ tiền sau khi đã hoàn.
    response = post_checked(
        "/internal/accounts/debit",
        original,
    )
    require_status(response, 200)
    assert response.json()["status"] == "REFUNDED"

    balance, entries = read_state(account["account_id"])
    assert balance == START_BALANCE
    assert entries == expected_entries

    print("PASS: hoàn một lần, không trừ lại giao dịch đã hoàn")


def test_competing_debits(account):
    print("\nTEST 4: Hai giao dịch cùng trừ 7 triệu từ số dư 10 triệu")

    payloads = [
        make_debit(account, "7000000.00"),
        make_debit(account, "7000000.00"),
    ]

    responses = post_parallel(
        "/internal/accounts/debit",
        payloads,
    )

    codes = sorted(
        response.status_code for response in responses
    )
    assert codes == [200, 409], (
        f"Cần một 200 và một 409, nhận {codes}. "
        f"Chi tiết: {[r.text for r in responses]}"
    )

    winner = None

    for payload, response in zip(payloads, responses):
        if response.status_code == 200:
            assert response.json()["status"] == "DEBITED"
            winner = payload["payment_id"]
        else:
            assert response.json()["detail"] == "Số dư không đủ"

    balance, entries = read_state(account["account_id"])

    assert balance == Decimal("3000000.00"), (
        f"Số dư sai: {balance}"
    )
    assert entries == [
        (winner, "DEBIT", Decimal("7000000.00"))
    ], f"Lịch sử không đúng: {entries}"

    print("PASS: chỉ một giao dịch thành công, còn 3 triệu")


def main():
    health = httpx.get(
        f"{BASE_URL}/health/db",
        timeout=10,
        trust_env=False,
    )
    health.raise_for_status()

    account_a = create_test_account("A")
    account_b = create_test_account("B")

    original = test_duplicate_debit(account_a)
    test_changed_payload(account_a, original)
    test_duplicate_refund(account_a, original)
    test_competing_debits(account_b)

    print("\nĐẠT 4/4 BÀI KIỂM TRA")
    print(
        "Đối chiếu SSMS bằng account_id:",
        account_a["account_id"],
        account_b["account_id"],
    )


if __name__ == "__main__":
    main()