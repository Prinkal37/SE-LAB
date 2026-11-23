"use client";
import { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { SubmissionDetail } from "@/lib/types";
import { useUser } from "@/components/useUser";
import StatusBadge from "@/components/StatusBadge";
import QuestionCard from "@/components/QuestionCard";

// Monaco is big, so it is only loaded on this page (design decision 4.7)
const CodeViewer = dynamic(() => import("@/components/CodeViewer"), {
  ssr: false,
  loading: () => <p>Loading editor...</p>,
});

const BUSY = ["UPLOADED", "ANALYSING", "GENERATING"];

// Review screen: flagged code on the left, viva questions on the right (FR-4.5.x)
export default function ReviewPage() {
  const user = useUser();
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const [sub, setSub] = useState<SubmissionDetail | null>(null);
  const [error, setError] = useState("");
  const [jump, setJump] = useState<{ line: number } | null>(null);

  const load = useCallback(() => {
    api.getSubmission(id).then(setSub).catch((e) => setError(e.message));
  }, [id]);
  useEffect(() => { load(); }, [load]);

  // keep polling until analysis and generation are finished
  useEffect(() => {
    if (!sub || !BUSY.includes(sub.status)) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [sub, load]);

  // run an API call, then reload the page data
  async function run(action: () => Promise<unknown>) {
    try { setError(""); await action(); load(); }
    catch (e) { setError((e as Error).message); }
  }

  if (!sub) return <p>{error || "Loading..."}</p>;

  const locked = sub.status === "APPROVED";
  const showReview = sub.status === "DRAFT" || sub.status === "APPROVED";

  return (
    <div>
      <p className="mb-2"><button className="underline" onClick={() => router.back()}>&larr; Back</button></p>
      <h1 className="mb-3 text-xl font-bold">Student {sub.student_ref} <StatusBadge status={sub.status} /></h1>
      {error && <p className="mb-2 text-red-600">{error}</p>}
      {BUSY.includes(sub.status) && <p>Analysing... this page refreshes by itself.</p>}
      {(sub.status === "PARSE_FAILED" || sub.status === "FAILED") && (
        <div className="card text-red-700">{sub.error ?? "This file could not be analysed."}</div>
      )}

      {showReview && (
        <div className="grid gap-4 md:grid-cols-3">
          <div className="md:col-span-2">
            <div className="card">
              <CodeViewer code={sub.code} findings={sub.findings} jumpTo={jump} />
            </div>
            <div className="card">
              <h2 className="mb-2 font-semibold">Flagged code</h2>
              <table className="w-full">
                <thead><tr><th className="th">Detector</th><th className="th">Lines</th><th className="th">Reason</th></tr></thead>
                <tbody>
                  {sub.findings.map((f, i) => (
                    <tr key={i}>
                      <td className="td">{f.detector}</td>
                      <td className="td">{f.start_line}-{f.end_line}</td>
                      <td className="td">{f.reason}</td>
                    </tr>
                  ))}
                  {sub.findings.length === 0 && <tr><td className="td" colSpan={3}>Nothing flagged. General questions were used.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>

          <div>
            <h2 className="mb-2 font-semibold">Viva questions</h2>
            {sub.questions.map((q) => (
              <QuestionCard
                key={q.id}
                q={q}
                locked={locked}
                onJump={() => setJump({ line: q.related_line })}
                onEdit={(text) => run(() => api.editQuestion(q.id, { question_text: text }))}
                onRegenerate={() => run(() => api.regenerate(q.id))}
                onDiscard={() => run(() => api.editQuestion(q.id, { state: "DISCARDED" }))}
              />
            ))}

            {!locked && user?.role === "INSTRUCTOR" && (
              <button
                className="btn"
                onClick={() => confirm("Approve this question set? It cannot be edited afterwards.") && run(() => api.approve(id))}
              >
                Approve question set
              </button>
            )}
            {!locked && user?.role !== "INSTRUCTOR" && (
              <p className="text-sm text-gray-600">Only the instructor can approve (BR-1).</p>
            )}
            {locked && (
              <div className="flex gap-3 text-sm">
                <a className="btn" href={api.exportUrl(id, "pdf")}>Export PDF</a>
                <a className="btn" href={api.exportUrl(id, "csv")}>Export CSV</a>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
