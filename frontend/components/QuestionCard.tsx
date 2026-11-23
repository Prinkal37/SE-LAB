"use client";
import { useState } from "react";
import type { Question } from "@/lib/types";

type Props = {
  q: Question;
  locked: boolean; // true after the set is approved
  onEdit: (text: string) => void;
  onRegenerate: () => void;
  onDiscard: () => void;
  onJump: () => void;
};

export default function QuestionCard({ q, locked, onEdit, onRegenerate, onDiscard, onJump }: Props) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(q.question_text);
  const discarded = q.state === "DISCARDED";

  function save() {
    // same limits as VivaQuestion in the report (Listing 5.2)
    if (text.trim().length < 15 || text.trim().length > 400) {
      alert("Question must be between 15 and 400 characters.");
      return;
    }
    onEdit(text.trim());
    setEditing(false);
  }

  return (
    <div className={`card ${discarded ? "opacity-50" : ""}`}>
      {editing ? (
        <textarea className="input w-full" rows={4} value={text} onChange={(e) => setText(e.target.value)} />
      ) : (
        <p className={discarded ? "line-through" : ""}>{q.question_text}</p>
      )}

      <p className="mt-1 text-xs text-gray-600">
        <button className="underline" onClick={onJump}>Line {q.related_line}</button> | {q.difficulty} | {q.state}
      </p>

      {!locked && !discarded && (
        <div className="mt-2 flex gap-2">
          {editing ? (
            <>
              <button className="btn" onClick={save}>Save</button>
              <button className="btn-gray" onClick={() => setEditing(false)}>Cancel</button>
            </>
          ) : (
            <>
              <button className="btn-gray" onClick={() => { setText(q.question_text); setEditing(true); }}>Edit</button>
              <button className="btn-gray" onClick={onRegenerate}>Regenerate</button>
              <button className="btn-gray" onClick={onDiscard}>Discard</button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
