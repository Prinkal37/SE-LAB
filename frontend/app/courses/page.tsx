"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Course } from "@/lib/types";
import { useUser } from "@/components/useUser";

// Dashboard: list of my courses (FR-4.1.2)
export default function CoursesPage() {
  const user = useUser();
  const [courses, setCourses] = useState<Course[]>([]);
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [term, setTerm] = useState("");
  const [error, setError] = useState("");

  function load() {
    api.listCourses().then(setCourses).catch((e) => setError(e.message));
  }
  useEffect(() => { load(); }, []);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.createCourse({ code, title, term });
      setCode(""); setTitle(""); setTerm("");
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div>
      <h1 className="mb-3 text-xl font-bold">My Courses</h1>
      {error && <p className="mb-2 text-red-600">{error}</p>}

      <table className="card w-full">
        <thead><tr><th className="th">Code</th><th className="th">Title</th><th className="th">Term</th><th className="th"></th></tr></thead>
        <tbody>
          {courses.map((c) => (
            <tr key={c.id}>
              <td className="td">{c.code}</td><td className="td">{c.title}</td><td className="td">{c.term}</td>
              <td className="td"><Link className="underline" href={`/courses/${c.id}`}>Open</Link></td>
            </tr>
          ))}
          {courses.length === 0 && <tr><td className="td" colSpan={4}>No courses yet.</td></tr>}
        </tbody>
      </table>

      {user?.role === "INSTRUCTOR" && (
        <form onSubmit={add} className="card flex flex-wrap gap-2">
          <input className="input" placeholder="Code (CSMC502)" value={code} onChange={(e) => setCode(e.target.value)} required />
          <input className="input" placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} required />
          <input className="input" placeholder="Term" value={term} onChange={(e) => setTerm(e.target.value)} required />
          <button className="btn" type="submit">Create course</button>
        </form>
      )}
    </div>
  );
}
