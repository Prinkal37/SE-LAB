// The only file that talks to the backend (see section 5.5 of the report).
// Every function matches an endpoint in Table 6.2.
import { mock } from "./mock";
import type { Assignment, Course, Question, Submission, SubmissionDetail, User } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const USE_MOCK = process.env.NEXT_PUBLIC_MOCK === "true";

// errors use the body shape from section 6.5: { error: { code, message } }
export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  if (USE_MOCK) {
    const out = mock(method, path, body);
    return (out === undefined ? undefined : JSON.parse(JSON.stringify(out))) as T; // copy so React sees changes
  }
  const isForm = body instanceof FormData;
  const res = await fetch(BASE + path, {
    method,
    credentials: "include", // sends the httpOnly JWT cookie
    headers: body && !isForm ? { "Content-Type": "application/json" } : undefined,
    body: body ? (isForm ? (body as FormData) : JSON.stringify(body)) : undefined,
  });
  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new ApiError(e?.error?.code ?? "UNKNOWN", e?.error?.message ?? "Something went wrong");
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  login: (email: string, password: string) => request<{ user: User }>("POST", "/auth/login", { email, password }),
  register: (email: string, password: string) => request<unknown>("POST", "/auth/register", { email, password }),

  listCourses: () => request<Course[]>("GET", "/courses"),
  createCourse: (c: Omit<Course, "id">) => request<Course>("POST", "/courses", c),
  addTA: (courseId: string, email: string) => request<unknown>("POST", `/courses/${courseId}/members`, { email }),

  listAssignments: (courseId: string) => request<Assignment[]>("GET", `/courses/${courseId}/assignments`),
  createAssignment: (courseId: string, title: string) =>
    request<Assignment>("POST", `/courses/${courseId}/assignments`, { title }),

  listSubmissions: (assignmentId: string) => request<Submission[]>("GET", `/assignments/${assignmentId}/submissions`),
  upload: (assignmentId: string, file: File, studentRef: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("student_ref", studentRef);
    return request<{ job_id: string }>("POST", `/assignments/${assignmentId}/submissions`, form);
  },

  getSubmission: (id: string) => request<SubmissionDetail>("GET", `/submissions/${id}`),
  editQuestion: (id: string, patch: Partial<Pick<Question, "question_text" | "state">>) =>
    request<Question>("PATCH", `/questions/${id}`, patch),
  regenerate: (id: string) => request<unknown>("POST", `/questions/${id}/regenerate`),
  approve: (submissionId: string) => request<unknown>("POST", `/submissions/${submissionId}/approve`),
  exportUrl: (submissionId: string, format: "pdf" | "csv") => `${BASE}/submissions/${submissionId}/export?format=${format}`,
};

// The JWT is in an httpOnly cookie, so JavaScript cannot read it.
// We only remember who is logged in (for showing the name and hiding buttons).
export const session = {
  get(): User | null {
    try { return JSON.parse(localStorage.getItem("user") || "null"); } catch { return null; }
  },
  save(u: User) { localStorage.setItem("user", JSON.stringify(u)); },
  clear() { localStorage.removeItem("user"); },
};
