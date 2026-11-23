"""Request dependencies: current user + course-level access checks (NFR-5.3.2, BR-1, BR-2)."""
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .errors import ApiError, forbidden, not_found
from .models import (
    ROLE_ADMIN,
    Assignment,
    Course,
    CourseMember,
    Question,
    Submission,
    User,
)
from .security import decode_token


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(get_settings().cookie_name)
    if not token:
        # Also accept "Authorization: Bearer <jwt>" (handy for Swagger / scripts).
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
    user_id = decode_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if not user or not user.password_hash:
        raise ApiError(401, "UNAUTHORIZED", "Please log in")
    return user


def membership(db: Session, user: User, course_id: str) -> CourseMember | None:
    return db.scalar(
        select(CourseMember).where(CourseMember.course_id == course_id, CourseMember.user_id == user.id)
    )


def require_course(db: Session, user: User, course_id: str, instructor_only: bool = False) -> Course:
    """Return the course if the user is a member (or admin). 404 for strangers so IDs don't leak."""
    course = db.get(Course, course_id)
    if not course:
        raise not_found("Course")
    if user.role == ROLE_ADMIN:
        return course
    m = membership(db, user, course_id)
    if not m:
        raise not_found("Course")
    if instructor_only and m.role != "INSTRUCTOR":
        raise forbidden("Only the course instructor can do this")
    return course


def require_assignment(db: Session, user: User, assignment_id: str, instructor_only: bool = False) -> Assignment:
    a = db.get(Assignment, assignment_id)
    if not a:
        raise not_found("Assignment")
    try:
        require_course(db, user, a.course_id, instructor_only)
    except ApiError as e:
        if e.status == 404:
            raise not_found("Assignment")
        raise
    return a


def require_submission(db: Session, user: User, submission_id: str) -> Submission:
    s = db.get(Submission, submission_id)
    if not s:
        raise not_found("Submission")
    try:
        require_assignment(db, user, s.assignment_id)
    except ApiError as e:
        if e.status == 404:
            raise not_found("Submission")
        raise
    return s


def require_question(db: Session, user: User, question_id: str) -> Question:
    q = db.get(Question, question_id)
    if not q:
        raise not_found("Question")
    try:
        require_submission(db, user, q.submission_id)
    except ApiError as e:
        if e.status == 404:
            raise not_found("Question")
        raise
    return q


def can_approve(db: Session, user: User, submission: Submission) -> bool:
    """BR-1: instructors approve. BR-2: TAs only if the instructor granted it."""
    if user.role == ROLE_ADMIN:
        return True
    m = membership(db, user, submission.assignment.course_id)
    return bool(m and (m.role == "INSTRUCTOR" or m.can_approve))
