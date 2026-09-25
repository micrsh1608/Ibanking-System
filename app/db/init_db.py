from app.db.database import Base, engine

from app.models.payment import PaymentTransaction
from app.models.account import Account
from app.models.tuition import TuitionFee


def init_db():
    Base.metadata.create_all(bind=engine)
    print("All tables created successfully!")


if __name__ == "__main__":
    init_db()