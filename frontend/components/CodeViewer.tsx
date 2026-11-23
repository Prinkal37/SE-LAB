"use client";
import Editor, { OnMount } from "@monaco-editor/react";
import { useEffect, useRef } from "react";
import type { Finding } from "@/lib/types";

type Props = { code: string; findings: Finding[]; jumpTo: { line: number } | null };

// Read-only Monaco editor with a highlighted line for each finding (design decision 4.7)
export default function CodeViewer({ code, findings, jumpTo }: Props) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const editorRef = useRef<any>(null);

  const onMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    editor.createDecorationsCollection(
      findings.map((f) => ({
        range: new monaco.Range(f.start_line, 1, f.end_line, 1),
        options: {
          isWholeLine: true,
          className: "flagged-line",
          glyphMarginClassName: "flagged-glyph",
          hoverMessage: { value: `**${f.detector}**: ${f.reason}` },
        },
      }))
    );
  };

  // scroll to a line when the instructor clicks "Line N" on a question
  useEffect(() => {
    if (jumpTo) {
      editorRef.current?.revealLineInCenter(jumpTo.line);
      editorRef.current?.setPosition({ lineNumber: jumpTo.line, column: 1 });
    }
  }, [jumpTo]);

  return (
    <Editor
      height="420px"
      language="python"
      value={code}
      onMount={onMount}
      options={{ readOnly: true, glyphMargin: true, minimap: { enabled: false }, scrollBeyondLastLine: false }}
    />
  );
}
