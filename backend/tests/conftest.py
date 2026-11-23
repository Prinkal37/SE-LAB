import os
import sys
from pathlib import Path

import pytest

# Test settings: SQLite file, inline jobs, offline template generator.
os.environ["DATABASE_URL"] = "sqlite:///./test_avg.db"
os.environ["QUEUE_MODE"] = "inline"
os.environ["LLM_MODEL"] = ""
os.environ["ENCRYPTION_KEY"] = "u6hQ0tPLNQ0yJk6S8m4v1hJ0V6Cq0m4m2l3V5g7q9_A="

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import db as dbmod  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

SAMPLE = '''def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

def show(nums):
    for a in nums:
        for b in nums:
            if a == b:
                print(a)
'''


@pytest.fixture(autouse=True)
def fresh_db():
    get_settings.cache_clear()
    dbmod.Base.metadata.drop_all(bind=dbmod.engine)
    dbmod.init_db()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def login(client, email, password="password123", register=True):
    if register:
        client.post("/api/v1/auth/register", json={"email": email, "password": password})
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["user"]


@pytest.fixture
def instructor(client):
    login(client, "prof@tezu.ac.in")
    return client


@pytest.fixture
def course_and_assignment(instructor):
    c = instructor.post("/api/v1/courses", json={"code": "CSMC502", "title": "SE Lab", "term": "Autumn 2026"}).json()
    a = instructor.post(f"/api/v1/courses/{c['id']}/assignments", json={"title": "A1"}).json()
    return c, a


def upload(client, assignment_id, code=SAMPLE, name="sol.py", ref="CSM25041"):
    return client.post(
        f"/api/v1/assignments/{assignment_id}/submissions",
        files={"file": (name, code.encode() if isinstance(code, str) else code)},
        data={"student_ref": ref},
    )
