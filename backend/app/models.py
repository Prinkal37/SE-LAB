"""Database tables.

User ─< CourseMember >─ Course ─< Assignment ─< Submission ─< Finding
                                                         └─< Question
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .config import get_settings
from .db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EncryptedText(TypeDecorator):
    """Text column encrypted with Fernet when ENCRYPTION_KEY is set (NFR-5.3.1)."""

    impl = Text
    cache_ok = True
    _PREFIX = "enc:"

    def _fernet(self) -> Optional[Fernet]:
        key = get_settings().encryption_key
        return Fernet(key.encode()) if key else None

    def process_bind_param(self, value, dialect):
        f = self._fernet()
        if value is None or f is None:
            return value
        return self._PREFIX + f.encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None or not value.startswith(self._PREFIX):
            return value
        f = self._fernet()
        if f is None:
            raise RuntimeError("Encrypted data found but ENCRYPTION_KEY is not set.")
        try:
            return f.decrypt(value[len(self._PREFIX):].encode()).decode()
        except InvalidToken as e:
            raise RuntimeError("Could not decrypt data: wrong ENCRYPTION_KEY.") from e


# Global roles (NFR-5.3.3)
ROLE_ADMIN, ROLE_INSTRUCTOR, ROLE_TA, ROLE_STUDENT = "ADMIN", "INSTRUCTOR", "TA", "STUDENT"

# Submission life cycle (frontend types.ts / Fig. 6.2)
S_UPLOADED, S_PARSE_FAILED, S_ANALYSING, S_GENERATING = "UPLOADED", "PARSE_FAILED", "ANALYSING", "GENERATING"
S_DRAFT, S_FAILED, S_APPROVED = "DRAFT", "FAILED", "APPROVED"
BUSY_STATUSES = {S_UPLOADED, S_ANALYSING, S_GENERATING}

# Question states
Q_DRAFT, Q_EDITED, Q_DISCARDED = "DRAFT", "EDITED", "DISCARDED"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    # NULL = invited by an instructor but not registered yet (FR-4.1.4)
    password_hash: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default=ROLE_INSTRUCTOR)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    memberships: Mapped[list["CourseMember"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    term: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    members: Mapped[list["CourseMember"]] = relationship(back_populates="course", cascade="all, delete-orphan")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="course", cascade="all, delete-orphan")


class CourseMember(Base):
    __tablename__ = "course_members"
    __table_args__ = (UniqueConstraint("course_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # INSTRUCTOR or TA
    # BR-2: instructor may grant a TA approval rights
    can_approve: Mapped[bool] = mapped_column(Boolean, default=False)

    course: Mapped[Course] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class Assignment(Base):
    __tablename__ = "assignments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(30), default="python")  # FR-4.1.3
    rubric: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # FR-4.1.3
    num_questions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # FR-4.4.5
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    course: Mapped[Course] = relationship(back_populates="assignments")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="assignment", cascade="all, delete-orphan")


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    student_ref: Mapped[str] = mapped_column(String(100), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    code: Mapped[str] = mapped_column(EncryptedText)
    status: Mapped[str] = mapped_column(String(20), default=S_UPLOADED, index=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    analysis: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # raw AST output (FR-4.7.2)
    generator: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # "llm:<model>" or "template"
    batch_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    uploaded_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    assignment: Mapped[Assignment] = relationship(back_populates="submissions")
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", order_by="Finding.start_line"
    )
    questions: Mapped[list["Question"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", order_by="Question.position"
    )


class Finding(Base):
    """One flagged code element (FR-4.3.4)."""

    __tablename__ = "findings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    detector: Mapped[str] = mapped_column(String(50))
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # function name
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    node_type: Mapped[str] = mapped_column(String(50))
    reason: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="info")

    submission: Mapped[Submission] = relationship(back_populates="findings")


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    finding_id: Mapped[Optional[str]] = mapped_column(ForeignKey("findings.id", ondelete="SET NULL"), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    question_text: Mapped[str] = mapped_column(Text)
    related_line: Mapped[int] = mapped_column(Integer)  # BR-3: always set
    related_node_type: Mapped[str] = mapped_column(String(50))
    difficulty: Mapped[str] = mapped_column(String(10))
    state: Mapped[str] = mapped_column(String(20), default=Q_DRAFT)
    # For general (fallback) questions with no finding, remember the target for regeneration.
    target: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    submission: Mapped[Submission] = relationship(back_populates="questions")
    finding: Mapped[Optional[Finding]] = relationship()
