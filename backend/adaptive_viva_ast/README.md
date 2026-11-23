# Adaptive Viva Generator — AST Engine

## Project structure

```text
adaptive_viva_ast/
├── __init__.py
├── ASTAnalyzer.py
├── main.py
├── models.py
└── requirements.txt
```

## Setup

Use Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run the API

Run this command from the directory that contains the `adaptive_viva_ast` folder:

```bash
uvicorn adaptive_viva_ast.main:app --reload
```

Open `http://127.0.0.1:8000/docs` to test the `/analyze` endpoint.

## Notes

- The analyzer parses source code; it does not execute uploaded Python files.
- Uploads are limited to 2 MiB.
- `complexity` is a simplified cyclomatic-complexity estimate, not a full control-flow-graph metric.
- The analyzer reports direct self-recursion and common `self.method()` recursion. It does not resolve indirect recursion across multiple functions.
