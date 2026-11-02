from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Unicode, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from services.tuition.database import Base


class Student(Base):
    __tablename__ = 'students'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mssv: Mapped[str] = mapped_column(String(24), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    invoices: Mapped[list['TuitionInvoice']] = relationship(back_populates='student')


class TuitionInvoice(Base):
    __tablename__ = 'tuition_invoices'
    __table_args__ = (
        UniqueConstraint('student_id', 'semester', name='uq_student_semester'),
        CheckConstraint('amount_due > 0', name='ck_tuition_positive'),
        CheckConstraint("status IN ('UNPAID','RESERVED','PAID')", name='ck_tuition_status'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(ForeignKey('students.id'), index=True)
    semester: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_due: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    status: Mapped[str] = mapped_column(String(12), nullable=False, default='UNPAID')
    reserved_payment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reserved_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_payment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    student: Mapped[Student] = relationship(back_populates='invoices')


class Reservation(Base):
    __tablename__ = 'tuition_reservations'
    __table_args__ = (CheckConstraint("status IN ('RESERVED','PAID','RELEASED')", name='ck_reservation_status'),)

    payment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_hash: Mapped[str | None] = mapped_column(String(64))
    mssv: Mapped[str | None] = mapped_column(String(24))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    status: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    items: Mapped[list['ReservationItem']] = relationship(back_populates='reservation', order_by='ReservationItem.invoice_id')


class ReservationItem(Base):
    __tablename__ = 'tuition_reservation_items'
    __table_args__ = (UniqueConstraint('payment_id', 'invoice_id', name='uq_reservation_invoice'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey('tuition_reservations.payment_id'))
    invoice_id: Mapped[int] = mapped_column(ForeignKey('tuition_invoices.id'))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    reservation: Mapped[Reservation] = relationship(back_populates='items')
