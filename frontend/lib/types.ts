// Types follow the interface contracts in the architecture report (Chapter 5 and 6)
export type Role = "ADMIN" | "INSTRUCTOR" | "TA" | "STUDENT";
export type User = { email: string; role: Role };
export type Course = { id: string; code: string; title: string; term: string };
export type Assignment = { id: string; title: string };

// submission life cycle, Fig. 6.2
export type Status = "UPLOADED" | "PARSE_FAILED" | "ANALYSING" | "GENERATING" | "DRAFT" | "FAILED" | "APPROVED";
export type Submission = { id: string; student_ref: string; status: Status };

export type Finding = {
  detector: string;
  name: string | null;
  start_line: number;
  end_line: number;
  reason: string;
};
export type Question = {
  id: string;
  question_text: string;
  related_line: number;
  difficulty: "easy" | "medium" | "hard";
  state: "DRAFT" | "EDITED" | "DISCARDED";
};
export type SubmissionDetail = Submission & {
  code: string;
  findings: Finding[];
  questions: Question[];
  error?: string;
};
