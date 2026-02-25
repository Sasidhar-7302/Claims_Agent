# Contributing

Thank you for contributing.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`.
4. Build vector index with `python index_db.py`.

## Development Workflow

1. Create a feature branch from `main`.
2. Keep changes focused and atomic.
3. Run tests locally: `python -m pytest tests/`.
4. Open a pull request with a clear summary and validation notes.

## Pull Request Checklist

- Code compiles and runs locally.
- Relevant tests pass.
- Documentation is updated if behavior changed.
- No secrets or generated artifacts are committed.
