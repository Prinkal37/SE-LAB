"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Submission } from "@/lib/types";
import { useUser } from "@/components/useUser";
import StatusBadge from "@/components/StatusBadge";

const MAX_BYTES = 5 * 1024 * 1024; // FR-4.2.3: reject files above 5 MB
const BUSY = ["UPLOADED", "ANALYSING", "GENERATING"];

// Upload submissions and see their status (FR-4.2.x)
export default function AssignmentPage() {
  useUser();
  const { id } = useParams<{ id: string }>();
  const [subs, setSubs] = useState<Submission[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0); // changing this clears the file input
  const [studentRef, setStudentRef] = useState("");
  const [error, setError] = useState("");

  function load() {
    api.listSubmissions(id).then(setSubs).catch((e) => setError(e.message));
  }
  useEffect(() => { load(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  // poll every 2 seconds while something is still being processed (section 3.4)
  useEffect(() => {
    if (!subs.some((s) => BUSY.includes(s.status))) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [subs]); // eslint-disable-line react-hooks/exhaustive-deps

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) { setError("Choose a .py or .zip file."); return; }
    if (!/\.(py|zip)$/i.test(file.name)) { setError("Only .py or .zip files are allowed."); return; }
    if (file.size > MAX_BYTES) { setError("File is larger than 5 MB."); return; }
    try {
      await api.upload(id, file, studentRef);
      setError(""); setFile(null); setStudentRef(""); setFileKey(fileKey + 1);
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div>
      <p className="mb-2"><Link className="underline" href="/courses">&larr; Courses</Link></p>
      <h1 className="mb-3 text-xl font-bold">Submissions</h1>
      {error && <p className="mb-2 text-red-600">{error}</p>}

      <form onSubmit={upload} className="card flex flex-wrap items-center gap-2">
        <input className="input" placeholder="Student roll no." value={studentRef} onChange={(e) => setStudentRef(e.target.value)} required />
        <input key={fileKey} type="file" accept=".py,.zip" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <button className="btn" type="submit">Upload</button>
      </form>

      <table className="card w-full">
        <thead><tr><th className="th">Student</th><th className="th">Status</th><th className="th"></th></tr></thead>
        <tbody>
          {subs.map((s) => (
            <tr key={s.id}>
              <td className="td">{s.student_ref}</td>
              <td className="td"><StatusBadge status={s.status} /></td>
              <td className="td"><Link className="underline" href={`/submissions/${s.id}`}>Open</Link></td>
            </tr>
          ))}
          {subs.length === 0 && <tr><td className="td" colSpan={3}>No submissions yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
