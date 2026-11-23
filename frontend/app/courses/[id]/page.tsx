"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Assignment } from "@/lib/types";
import { useUser } from "@/components/useUser";

// One course: its assignments (FR-4.1.3) and adding TAs (FR-4.1.4)
export default function CoursePage() {
  const user = useUser();
  const { id } = useParams<{ id: string }>();
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [title, setTitle] = useState("");
  const [taEmail, setTaEmail] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  function load() {
    api.listAssignments(id).then(setAssignments).catch((e) => setError(e.message));
  }
  useEffect(() => { load(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function addAssignment(e: React.FormEvent) {
    e.preventDefault();
    try { await api.createAssignment(id, title); setTitle(""); load(); }
    catch (err) { setError((err as Error).message); }
  }
  async function addTA(e: React.FormEvent) {
    e.preventDefault();
    try { await api.addTA(id, taEmail); setInfo("TA added: " + taEmail); setTaEmail(""); }
    catch (err) { setError((err as Error).message); }
  }

  const isInstructor = user?.role === "INSTRUCTOR";
  return (
    <div>
      <p className="mb-2"><Link className="underline" href="/courses">&larr; All courses</Link></p>
      <h1 className="mb-3 text-xl font-bold">Assignments</h1>
      {error && <p className="mb-2 text-red-600">{error}</p>}
      {info && <p className="mb-2 text-green-700">{info}</p>}

      <table className="card w-full">
        <thead><tr><th className="th">Title</th><th className="th"></th></tr></thead>
        <tbody>
          {assignments.map((a) => (
            <tr key={a.id}>
              <td className="td">{a.title}</td>
              <td className="td"><Link className="underline" href={`/assignments/${a.id}`}>Open</Link></td>
            </tr>
          ))}
          {assignments.length === 0 && <tr><td className="td" colSpan={2}>No assignments yet.</td></tr>}
        </tbody>
      </table>

      {isInstructor && (
        <>
          <form onSubmit={addAssignment} className="card flex gap-2">
            <input className="input" placeholder="Assignment title" value={title} onChange={(e) => setTitle(e.target.value)} required />
            <button className="btn" type="submit">Create assignment</button>
          </form>
          <form onSubmit={addTA} className="card flex gap-2">
            <input className="input" type="email" placeholder="TA email" value={taEmail} onChange={(e) => setTaEmail(e.target.value)} required />
            <button className="btn" type="submit">Add TA</button>
          </form>
        </>
      )}
    </div>
  );
}
