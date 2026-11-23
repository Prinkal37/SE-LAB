"""FR-4.1.2 courses, FR-4.1.3 assignments, FR-4.1.4 TAs."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, membership, require_course
from ..errors import bad_request, conflict, forbidden, not_found
from ..models import ROLE_ADMIN, ROLE_INSTRUCTOR, ROLE_TA, Assignment, Course, CourseMember, User
from ..schemas import (
    AssignmentIn,
    AssignmentOut,
    CourseIn,
    CourseOut,
    CourseUpdate,
    MemberIn,
    MemberOut,
    MemberUpdate,
)

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("", response_model=list[CourseOut])
def list_courses(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role == ROLE_ADMIN:
        return db.scalars(select(Course).order_by(Course.created_at)).all()
    return db.scalars(
        select(Course).join(CourseMember).where(CourseMember.user_id == user.id).order_by(Course.created_at)
    ).all()


@router.post("", response_model=CourseOut, status_code=201)
def create_course(body: CourseIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in (ROLE_INSTRUCTOR, ROLE_ADMIN):
        raise forbidden("Only instructors can create courses")
    course = Course(**body.model_dump())
    course.members.append(CourseMember(user=user, role="INSTRUCTOR", can_approve=True))
    db.add(course)
    db.commit()
    return course


@router.get("/{course_id}", response_model=CourseOut)
def get_course(course_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return require_course(db, user, course_id)


@router.patch("/{course_id}", response_model=CourseOut)
def update_course(course_id: str, body: CourseUpdate, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    course = require_course(db, user, course_id, instructor_only=True)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(course, k, v)
    db.commit()
    return course


@router.delete("/{course_id}", status_code=204)
def delete_course(course_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(require_course(db, user, course_id, instructor_only=True))
    db.commit()


# ---------------- members (TAs)
def _member_out(m: CourseMember) -> MemberOut:
    return MemberOut(user_id=m.user_id, email=m.user.email, role=m.role, can_approve=m.can_approve,
                     registered=m.user.password_hash is not None)


@router.get("/{course_id}/members", response_model=list[MemberOut])
def list_members(course_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course = require_course(db, user, course_id)
    return [_member_out(m) for m in course.members]


@router.post("/{course_id}/members", response_model=MemberOut, status_code=201)
def add_ta(course_id: str, body: MemberIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Add a TA. Unknown emails get an invited account they claim by registering with that email."""
    require_course(db, user, course_id, instructor_only=True)
    email = body.email.lower()
    ta = db.scalar(select(User).where(User.email == email))
    if ta is None:
        ta = User(email=email, password_hash=None, role=ROLE_TA)
        db.add(ta)
        db.flush()
    if ta.id == user.id:
        raise bad_request("You are already the instructor of this course")
    if membership(db, ta, course_id):
        raise conflict(f"{email} is already a member of this course")
    m = CourseMember(course_id=course_id, user_id=ta.id, role="TA", can_approve=body.can_approve)
    db.add(m)
    db.commit()
    db.refresh(m)
    return _member_out(m)


@router.patch("/{course_id}/members/{user_id}", response_model=MemberOut)
def update_member(course_id: str, user_id: str, body: MemberUpdate, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """BR-2: instructor grants/revokes a TA's approval permission."""
    require_course(db, user, course_id, instructor_only=True)
    m = db.scalar(select(CourseMember).where(CourseMember.course_id == course_id, CourseMember.user_id == user_id))
    if not m or m.role != "TA":
        raise not_found("TA")
    m.can_approve = body.can_approve
    db.commit()
    return _member_out(m)


@router.delete("/{course_id}/members/{user_id}", status_code=204)
def remove_member(course_id: str, user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_course(db, user, course_id, instructor_only=True)
    m = db.scalar(select(CourseMember).where(CourseMember.course_id == course_id, CourseMember.user_id == user_id))
    if not m or m.role != "TA":
        raise not_found("TA")
    db.delete(m)
    db.commit()


# ---------------- assignments
@router.get("/{course_id}/assignments", response_model=list[AssignmentOut])
def list_assignments(course_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course = require_course(db, user, course_id)
    return sorted(course.assignments, key=lambda a: a.created_at)


@router.post("/{course_id}/assignments", response_model=AssignmentOut, status_code=201)
def create_assignment(course_id: str, body: AssignmentIn, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    require_course(db, user, course_id, instructor_only=True)
    a = Assignment(course_id=course_id, **body.model_dump())
    db.add(a)
    db.commit()
    return a
