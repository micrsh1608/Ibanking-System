from sqlalchemy import Column, Integer, String, Numeric

from app.db.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)

    full_name = Column(
        String(100),
        nullable=False
    )

    email = Column(
        String(150),
        unique=True,
        nullable=False
    )

    balance = Column(
        Numeric(15, 2),
        nullable=False,
        default=0
    )