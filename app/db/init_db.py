from app.db.database import Base, engine

from app.payment_models.payment import PaymentTransaction
from app.payment_models.account import Account
from app.payment_models.tuition import TuitionFee


def init_db():
    Base.metadata.create_all(bind=engine)
    print("All tables created successfully!")


if __name__ == "__main__":
    init_db()