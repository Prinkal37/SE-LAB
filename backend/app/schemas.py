"""Request/response bodies. Field names match frontend/lib/types.ts exactly."""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Difficulty = Literal["easy", "medium", "hard"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth ----
class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(ORM):
    email: str
    role: str


class LoginOut(BaseModel):
    user: UserOut


# ---- courses ----
class CourseIn(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=200)
    term: str = Field(min_length=1, max_length=100)


class CourseUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    term: Optional[str] = Field(default=None, min_length=1, max_length=100)


class CourseOut(ORM):
    id: str
    code: str
    title: str
    term: str


class MemberIn(BaseModel):
    email: EmailStr
    can_approve: bool = False


class MemberUpdate(BaseModel):
    can_approve: bool


class MemberOut(BaseModel):
    user_id: str
    email: str
    role: str
    can_approve: bool
    registered: bool


# ---- assignments ----
class AssignmentIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    language: Literal["python"] = "python"
    rubric: Optional[dict] = None
    num_questions: Optional[int] = Field(default=None, ge=1, le=10)


class AssignmentUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    rubric: Optional[dict] = None
    num_questions: Optional[int] = Field(default=None, ge=1, le=10)


class AssignmentOut(ORM):
    id: str
    title: str
    language: str
    rubric: Optional[dict] = None
    num_questions: Optional[int] = None


# ---- submissions ----
class SubmissionOut(ORM):
    id: str
    student_ref: str
    status: str


class UploadOut(BaseModel):
    job_id: str
    submission_ids: list[str]
    rejected: list[dict] = []


class FindingOut(ORM):
    detector: str
    name: Optional[str]
    start_line: int
    end_line: int
    reason: str
    node_type: str
    severity: str


class QuestionOut(ORM):
    id: str
    question_text: str
    related_line: int
    related_node_type: str
    difficulty: str
    state: str


class SubmissionDetailOut(SubmissionOut):
    code: str
    filename: str
    findings: list[FindingOut]
    questions: list[QuestionOut]
    error: Optional[str] = None
    generator: Optional[str] = None


class QuestionPatch(BaseModel):
    question_text: Optional[str] = Field(default=None, min_length=15, max_length=400)
    state: Optional[Literal["DRAFT", "DISCARDED"]] = None
