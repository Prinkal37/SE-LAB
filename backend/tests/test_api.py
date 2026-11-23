import io
import zipfile

from conftest import SAMPLE, login, upload

API = "/api/v1"


# ---------------- auth (FR-4.1.1, NFR-5.3.4)
def test_register_login_and_cookie(client):
    r = client.post(f"{API}/auth/register", json={"email": "a@x.com", "password": "password123"})
    assert r.status_code == 201
    assert r.json()["user"] == {"email": "a@x.com", "role": "INSTRUCTOR"}
    r = client.post(f"{API}/auth/login", json={"email": "a@x.com", "password": "password123"})
    assert r.status_code == 200
    assert "avg_token" in r.cookies
    assert client.get(f"{API}/auth/me").json()["email"] == "a@x.com"


def test_password_is_hashed(client):
    from app import db as dbmod
    from app.models import User

    client.post(f"{API}/auth/register", json={"email": "a@x.com", "password": "password123"})
    with dbmod.SessionLocal() as s:
        u = s.query(User).one()
        assert u.password_hash != "password123" and u.password_hash.startswith("$2")


def test_bad_login_and_error_shape(client):
    r = client.post(f"{API}/auth/login", json={"email": "no@x.com", "password": "password123"})
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "INVALID_CREDENTIALS", "message": "Wrong email or password"}}


def test_duplicate_register(client):
    client.post(f"{API}/auth/register", json={"email": "a@x.com", "password": "password123"})
    r = client.post(f"{API}/auth/register", json={"email": "a@x.com", "password": "password123"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_TAKEN"


def test_requires_login(client):
    r = client.get(f"{API}/courses")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"


# ---------------- courses / assignments (FR-4.1.2, FR-4.1.3)
def test_course_crud(instructor):
    c = instructor.post(f"{API}/courses", json={"code": "CS1", "title": "T", "term": "X"}).json()
    assert set(c) == {"id", "code", "title", "term"}
    assert instructor.get(f"{API}/courses").json() == [c]
    r = instructor.patch(f"{API}/courses/{c['id']}", json={"title": "New"})
    assert r.json()["title"] == "New"
    assert instructor.delete(f"{API}/courses/{c['id']}").status_code == 204
    assert instructor.get(f"{API}/courses").json() == []


def test_assignments(course_and_assignment, instructor):
    c, a = course_and_assignment
    assert a["title"] == "A1" and a["language"] == "python"
    assert [x["id"] for x in instructor.get(f"{API}/courses/{c['id']}/assignments").json()] == [a["id"]]


def test_other_instructor_cannot_see_course(client, course_and_assignment):
    c, a = course_and_assignment
    login(client, "other@x.com")
    assert client.get(f"{API}/courses").json() == []
    assert client.get(f"{API}/courses/{c['id']}/assignments").status_code == 404
    assert upload(client, a["id"]).status_code == 404


# ---------------- pipeline (FR-4.2, 4.3, 4.4)
def test_upload_analyse_generate(instructor, course_and_assignment):
    _, a = course_and_assignment
    r = upload(instructor, a["id"])
    assert r.status_code == 202
    sid = r.json()["job_id"]
    subs = instructor.get(f"{API}/assignments/{a['id']}/submissions").json()
    assert subs == [{"id": sid, "student_ref": "CSM25041", "status": "DRAFT"}]

    d = instructor.get(f"{API}/submissions/{sid}").json()
    assert d["code"] == SAMPLE
    detectors = {f["detector"] for f in d["findings"]}
    assert {"recursion", "nested_loops"} <= detectors
    assert 3 <= len(d["questions"]) <= 5  # FR-4.4.5 default
    for q in d["questions"]:  # BR-3 + schema
        assert q["related_line"] >= 1 and q["difficulty"] in ("easy", "medium", "hard")
        assert 15 <= len(q["question_text"]) <= 400 and q["state"] == "DRAFT"
    # every finding that was picked has a question referencing a line inside it
    rec = next(f for f in d["findings"] if f["detector"] == "recursion")
    assert any(rec["start_line"] <= q["related_line"] <= rec["end_line"] for q in d["questions"])


def test_code_encrypted_at_rest(instructor, course_and_assignment):
    from sqlalchemy import text

    from app import db as dbmod

    _, a = course_and_assignment
    upload(instructor, a["id"])
    with dbmod.engine.connect() as c:
        raw = c.execute(text("SELECT code FROM submissions")).scalar()
    assert raw.startswith("enc:") and "fib" not in raw


def test_syntax_error_reported(instructor, course_and_assignment):
    _, a = course_and_assignment
    sid = upload(instructor, a["id"], code="def f(:\n  pass\n").json()["job_id"]
    d = instructor.get(f"{API}/submissions/{sid}").json()
    assert d["status"] == "PARSE_FAILED"
    assert "line 1" in d["error"]


def test_trivial_code_gets_general_questions(instructor, course_and_assignment):
    _, a = course_and_assignment
    sid = upload(instructor, a["id"], code="def add(a, b):\n    return a + b\n").json()["job_id"]
    d = instructor.get(f"{API}/submissions/{sid}").json()
    assert d["status"] == "DRAFT" and d["findings"] == []
    assert len(d["questions"]) >= 1
    assert all(q["related_line"] == 1 for q in d["questions"])


def test_wrong_extension_and_size(instructor, course_and_assignment):
    _, a = course_and_assignment
    r = upload(instructor, a["id"], name="x.txt")
    assert r.status_code == 400 and r.json()["error"]["code"] == "UNSUPPORTED_FILE"
    r = upload(instructor, a["id"], code=b"#" * (5 * 1024 * 1024 + 10))
    assert r.status_code == 413


def test_zip_batch_upload(instructor, course_and_assignment):
    _, a = course_and_assignment
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("batch/CSM001.py", SAMPLE)
        z.writestr("batch/CSM002/main.py", "def g(x):\n    while x:\n        x -= 1\n")
        z.writestr("batch/CSM002/util.py", "def h():\n    return {1: 2}\n")
        z.writestr("batch/CSM003.py", "def bad(:\n")
        z.writestr("batch/readme.txt", "ignore me")
        z.writestr("__MACOSX/batch/._CSM001.py", "junk")
    r = upload(instructor, a["id"], code=buf.getvalue(), name="batch.zip", ref="")
    assert r.status_code == 202, r.text
    assert len(r.json()["submission_ids"]) == 3
    subs = {s["student_ref"]: s["status"] for s in instructor.get(f"{API}/assignments/{a['id']}/submissions").json()}
    assert subs == {"CSM001": "DRAFT", "CSM002": "DRAFT", "CSM003": "PARSE_FAILED"}


# ---------------- review (FR-4.5.x)
def _draft(instructor, a):
    sid = upload(instructor, a["id"]).json()["job_id"]
    return sid, instructor.get(f"{API}/submissions/{sid}").json()


def test_edit_discard_restore(instructor, course_and_assignment):
    _, a = course_and_assignment
    sid, d = _draft(instructor, a)
    q = d["questions"][0]
    r = instructor.patch(f"{API}/questions/{q['id']}", json={"question_text": "Explain the base case of fib on line 2."})
    assert r.json()["state"] == "EDITED" and r.json()["question_text"].startswith("Explain")
    assert instructor.patch(f"{API}/questions/{q['id']}", json={"question_text": "short"}).status_code == 422
    assert instructor.patch(f"{API}/questions/{q['id']}", json={"state": "DISCARDED"}).json()["state"] == "DISCARDED"
    assert instructor.patch(f"{API}/questions/{q['id']}", json={"state": "DRAFT"}).json()["state"] == "DRAFT"


def test_regenerate_only_one(instructor, course_and_assignment):
    _, a = course_and_assignment
    sid, d = _draft(instructor, a)
    q0, rest = d["questions"][0], d["questions"][1:]
    r = instructor.post(f"{API}/questions/{q0['id']}/regenerate")
    assert r.status_code == 200
    assert r.json()["question_text"] != q0["question_text"]
    after = instructor.get(f"{API}/submissions/{sid}").json()["questions"]
    assert [q["question_text"] for q in after[1:]] == [q["question_text"] for q in rest]


def test_approve_locks_and_exports(instructor, course_and_assignment):
    _, a = course_and_assignment
    sid, d = _draft(instructor, a)
    assert instructor.get(f"{API}/submissions/{sid}/export?format=csv").status_code == 409  # not approved yet
    instructor.patch(f"{API}/questions/{d['questions'][0]['id']}", json={"state": "DISCARDED"})
    assert instructor.post(f"{API}/submissions/{sid}/approve").status_code == 200
    assert instructor.get(f"{API}/submissions/{sid}").json()["status"] == "APPROVED"
    q = d["questions"][1]
    assert instructor.patch(f"{API}/questions/{q['id']}", json={"state": "DISCARDED"}).status_code == 409

    csv = instructor.get(f"{API}/submissions/{sid}/export?format=csv")
    assert csv.status_code == 200 and "text/csv" in csv.headers["content-type"]
    lines = csv.content.decode("utf-8-sig").strip().splitlines()
    assert len(lines) == 1 + len(d["questions"]) - 1  # header + non-discarded
    pdf = instructor.get(f"{API}/submissions/{sid}/export?format=pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


# ---------------- TAs (FR-4.1.4, BR-1, BR-2)
def test_ta_flow(client):
    login(client, "prof@x.com")
    c = client.post(f"{API}/courses", json={"code": "C", "title": "T", "term": "X"}).json()
    a = client.post(f"{API}/courses/{c['id']}/assignments", json={"title": "A1"}).json()
    r = client.post(f"{API}/courses/{c['id']}/members", json={"email": "ta@x.com"})
    assert r.status_code == 201 and r.json()["registered"] is False

    # invited TA registers and keeps the TA role
    user = login(client, "ta@x.com")
    assert user["role"] == "TA"
    assert [x["id"] for x in client.get(f"{API}/courses").json()] == [c["id"]]
    assert client.post(f"{API}/courses", json={"code": "Z", "title": "Z", "term": "Z"}).status_code == 403
    assert client.post(f"{API}/courses/{c['id']}/assignments", json={"title": "B"}).status_code == 403

    sid = upload(client, a["id"]).json()["job_id"]  # TA can upload
    q = client.get(f"{API}/submissions/{sid}").json()["questions"][0]
    assert client.patch(f"{API}/questions/{q['id']}", json={"question_text": "TA edited this question text."}).status_code == 200
    r = client.post(f"{API}/submissions/{sid}/approve")
    assert r.status_code == 403  # BR-1

    # BR-2: instructor grants approval permission
    login(client, "prof@x.com", register=False)
    ta_id = next(m["user_id"] for m in client.get(f"{API}/courses/{c['id']}/members").json() if m["role"] == "TA")
    client.patch(f"{API}/courses/{c['id']}/members/{ta_id}", json={"can_approve": True})
    login(client, "ta@x.com", register=False)
    assert client.post(f"{API}/submissions/{sid}/approve").status_code == 200


def test_health(client):
    r = client.get("/health").json()
    assert r["database"] == "ok" and r["llm"] == "template"
