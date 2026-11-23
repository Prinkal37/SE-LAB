from fastapi import FastAPI, File, HTTPException, UploadFile

from .ASTAnalyzer import analyze_code

app = FastAPI(title="Adaptive Viva Generator - AST Engine")

MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MiB


@app.get("/")
def root():
    return {
        "message": "Adaptive Viva Generator AST Engine",
        "status": "running",
    }


@app.post("/analyze")
async def analyze_python_file(file: UploadFile = File(...)):
    filename = file.filename or ""
    if not filename.lower().endswith(".py"):
        raise HTTPException(
            status_code=400,
            detail="Only Python (.py) files are supported.",
        )

    # Read one byte beyond the limit so oversized uploads can be rejected.
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large. Maximum size is {MAX_UPLOAD_BYTES} bytes.",
        )

    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        source_code = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="File must be UTF-8 encoded.",
        )

    result = analyze_code(source_code)
    return result.to_dict()
