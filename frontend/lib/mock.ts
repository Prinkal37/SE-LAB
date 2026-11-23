// Fake backend so the screens work before the real API is ready.
// Turn it on with NEXT_PUBLIC_MOCK=true in .env.local. Data resets on page refresh.
import type { Assignment, Course, SubmissionDetail } from "./types";

const code = `def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

def show(nums):
    for a in nums:
        for b in nums:
            if a == b:
                print(a)
`;

const findings = [
  { detector: "recursion", name: "fib", start_line: 1, end_line: 4, reason: "fib calls itself; no memoisation" },
  { detector: "nested_loops", name: "show", start_line: 7, end_line: 10, reason: "loop inside loop (possible O(n^2))" },
];
const questions = [
  { id: "q1", question_text: "Your fib() on line 4 calls itself twice. How many calls happen for fib(30)?", related_line: 4, difficulty: "medium" as const, state: "DRAFT" as const },
  { id: "q2", question_text: "Why did you use two nested loops in show() on line 8? Can it be done faster?", related_line: 8, difficulty: "hard" as const, state: "DRAFT" as const },
];

const courses: Course[] = [{ id: "c1", code: "CSMC502", title: "Software Engineering Lab", term: "Autumn 2026" }];
const assignments: Assignment[] = [{ id: "a1", title: "Assignment 1: Recursion" }];
const subs: SubmissionDetail[] = [
  { id: "s1", student_ref: "CSM25041", status: "DRAFT", code, findings, questions },
];

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function mock(method: string, path: string, body?: any): any {
  const p = path.split("?")[0].split("/").filter(Boolean); // "/courses/c1/assignments" -> ["courses","c1","assignments"]

  if (p[0] === "auth" && p[1] === "login") {
    // in the mock, emails starting with "ta" log in as a TA
    return { user: { email: body.email, role: body.email.startsWith("ta") ? "TA" : "INSTRUCTOR" } };
  }
  if (p[0] === "auth") return {};

  if (p[0] === "courses" && p.length === 1) {
    if (method === "POST") { const c = { id: "c" + (courses.length + 1), ...body }; courses.push(c); return c; }
    return courses;
  }
  if (p[0] === "courses" && p[2] === "assignments") {
    if (method === "POST") { const a = { id: "a" + (assignments.length + 1), title: body.title }; assignments.push(a); return a; }
    return assignments; // same list for every course in the mock
  }
  if (p[0] === "courses" && p[2] === "members") return {};

  if (p[0] === "assignments" && p[2] === "submissions") {
    if (method === "POST") {
      const n = subs.length + 1;
      const s: SubmissionDetail = {
        id: "s" + n, student_ref: String(body.get("student_ref")), status: "ANALYSING",
        code, findings, questions: questions.map((q) => ({ ...q, id: q.id + "-" + n })),
      };
      subs.push(s);
      setTimeout(() => { s.status = "DRAFT"; }, 4000); // pretend the worker needs 4 seconds
      return { job_id: s.id };
    }
    return subs.map((s) => ({ id: s.id, student_ref: s.student_ref, status: s.status }));
  }

  if (p[0] === "submissions") {
    const s = subs.find((x) => x.id === p[1]);
    if (!s) throw new Error("Submission not found");
    if (p[2] === "approve") { s.status = "APPROVED"; return {}; }
    return s;
  }

  if (p[0] === "questions") {
    const q = subs.flatMap((s) => s.questions).find((x) => x.id === p[1]);
    if (!q) throw new Error("Question not found");
    if (p[2] === "regenerate") { q.question_text = "(regenerated) Explain what happens at line " + q.related_line + " step by step."; q.state = "DRAFT"; return {}; }
    if (body.question_text) { q.question_text = body.question_text; q.state = "EDITED"; }
    if (body.state) q.state = body.state;
    return q;
  }
  throw new Error("Mock: unknown route " + method + " " + path);
}
