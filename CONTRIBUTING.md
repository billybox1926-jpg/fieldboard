# Contributing to fieldboard

Thank you for your interest in contributing!

## Development Setup

```bash
git clone https://github.com/billybox1926-jpg/fieldboard.git
cd fieldboard
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest ruff pre-commit
pre-commit install
```

## Running Tests

```bash
pytest tests/ -v
```

## Code Style

- Follow PEP 8
- Use type hints where appropriate
- Keep functions focused and small
