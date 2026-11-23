const colors: Record<string, string> = {
  DRAFT: "bg-yellow-200", APPROVED: "bg-green-200", FAILED: "bg-red-200", PARSE_FAILED: "bg-red-200",
  ANALYSING: "bg-blue-200", GENERATING: "bg-blue-200", UPLOADED: "bg-gray-200",
};

export default function StatusBadge({ status }: { status: string }) {
  return <span className={`rounded px-2 py-0.5 text-xs ${colors[status] ?? "bg-gray-200"}`}>{status}</span>;
}
