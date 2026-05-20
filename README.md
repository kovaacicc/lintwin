# lintwin

Keep your Linux machines in sync.

## Prerequisites

- Python 3.11+
- `git`, `rsync`
- `gh` (GitHub CLI) authenticated: `gh auth login`
- SSH key-based auth to remote machines

## Install

```bash
pip install -e .
```

## Quick start

```bash
# First machine:
lintwin init

# Every other machine:
lintwin init --join git@github.com:you/your-dots.git

# Daily use:
lintwin sync
```
