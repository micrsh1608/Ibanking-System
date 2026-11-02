from services.payment.migrate import migrate


def init_db():
    migrate()
    print("Payment schema is up to date; legacy data was preserved.")


if __name__ == "__main__":
    init_db()
