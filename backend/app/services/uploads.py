"""Turn an uploaded .py or .zip into per-student source files (FR-4.2.1 - FR-4.2.3).

Zip layout rules (FR-4.2.2):
  * A single wrapping folder (e.g. `batch1/...`) is ignored.
  * `ROLL/anything.py`  -> student = ROLL (several files are joined in name order).
  * `ROLL.py` at the top -> student = ROLL.
Non-.py files, hidden files and __MACOSX entries are skipped.
"""
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from ..config import get_settings
from ..errors import ApiError, bad_request


@dataclass
class SourceFile:
    student_ref: str
    filename: str
    code: str


def _decode(data: bytes, name: str) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise bad_request(f"{name} is not UTF-8 text.", "BAD_ENCODING")


def _clean_ref(ref: str) -> str:
    ref = re.sub(r"[^A-Za-z0-9_.\-]", "_", ref.strip())[:100]
    return ref or "unknown"


def from_single(filename: str, data: bytes, student_ref: str) -> SourceFile:
    if len(data) > get_settings().max_file_bytes:
        raise ApiError(413, "FILE_TOO_LARGE", f"{filename} is larger than the {_mb()} MB limit.")
    if not data.strip():
        raise bad_request("Uploaded file is empty.", "EMPTY_FILE")
    if not student_ref.strip():
        raise bad_request("student_ref is required for a single-file upload.")
    return SourceFile(_clean_ref(student_ref), filename, _decode(data, filename))


def from_zip(data: bytes) -> tuple[list[SourceFile], list[dict]]:
    s = get_settings()
    if len(data) > s.max_zip_bytes:
        raise ApiError(413, "FILE_TOO_LARGE", f"Zip is larger than {s.max_zip_bytes // (1024 * 1024)} MB.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise bad_request("Not a valid .zip file.", "BAD_ZIP")

    members = []
    for info in zf.infolist():
        p = PurePosixPath(info.filename)
        if info.is_dir() or p.suffix.lower() != ".py":
            continue
        if any(part.startswith(".") or part == "__MACOSX" for part in p.parts):
            continue
        members.append((p, info))
    if not members:
        raise bad_request("The zip contains no .py files.", "EMPTY_ZIP")
    if len(members) > s.max_zip_members:
        raise bad_request(f"Too many files in zip (max {s.max_zip_members}).")

    # strip one common wrapping folder
    parts = [p.parts for p, _ in members]
    if all(len(x) > 1 for x in parts) and len({x[0] for x in parts}) == 1:
        parts = [x[1:] for x in parts]

    grouped: dict[str, list[tuple[str, zipfile.ZipInfo]]] = {}
    for rel, (_, info) in zip(parts, members):
        ref = rel[0] if len(rel) > 1 else PurePosixPath(rel[0]).stem
        grouped.setdefault(_clean_ref(ref), []).append(("/".join(rel), info))

    files: list[SourceFile] = []
    rejected: list[dict] = []
    for ref, items in sorted(grouped.items()):
        items.sort(key=lambda x: x[0])
        chunks, too_big = [], None
        for name, info in items:
            if info.file_size > s.max_file_bytes:  # checked before decompressing (zip-bomb guard)
                too_big = name
                break
            with zf.open(info) as fh:
                raw = fh.read(s.max_file_bytes + 1)
            if len(raw) > s.max_file_bytes:
                too_big = name
                break
            try:
                chunks.append((name, _decode(raw, name)))
            except ApiError as e:
                rejected.append({"student_ref": ref, "file": name, "reason": e.message})
                chunks = []
                break
        if too_big:
            rejected.append({"student_ref": ref, "file": too_big, "reason": f"larger than {_mb()} MB"})
            continue
        if not chunks:
            continue
        if len(chunks) == 1:
            code = chunks[0][1]
        else:
            code = "\n".join(f"# ===== file: {n} =====\n{c.rstrip()}\n" for n, c in chunks)
        if not code.strip():
            rejected.append({"student_ref": ref, "file": items[0][0], "reason": "empty file"})
            continue
        files.append(SourceFile(ref, ", ".join(n for n, _ in chunks), code))
    return files, rejected


def _mb() -> int:
    return get_settings().max_file_bytes // (1024 * 1024)
