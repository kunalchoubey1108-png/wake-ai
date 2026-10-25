# wake.md / wake.lock.json specification

## Purpose

`wake.md` is the human-readable **graveyard** of removals Wake.ai performed.  
`wake.lock.json` is the machine-readable lockfile used to **resurrect** code exactly.

Both are written at the repo root (or a configurable path) after a successful cleanup job.

---

## `wake.md` format

Markdown document with a short header, then one section per removal.

```markdown
# Wake.ai graveyard

- Repo: https://github.com/example/flask-blog
- Base commit: `a1b2c3d4e5f6789012345678901234567890abcd`
- Job id: `job_20261103_001`
- Generated (UTC): 2026-11-03T18:42:11Z

## Removals

### `rm_0001` — unused_slugify
- **File:** `src/flask_blog/app.py`
- **Reason:** Vulture: unused function; LLM triage: safe; pytest: pass
- **Depends on:** _(none)_
- **Resurrect:** `wake resurrect rm_0001`

Removed hunk:

\`\`\`python
def unused_slugify(title: str) -> str:
    """Planted dead function."""
    return title.lower().replace(" ", "-")
\`\`\`
```

### Example entry (complete)

### `rm_0002` — DraftCache
- **File:** `src/flask_blog/app.py`
- **Reason:** Vulture: unused class; ruff F401 N/A; pytest: pass
- **Depends on:** `rm_0001` _(optional ordering hint)_
- **Resurrect:** `wake resurrect rm_0002`

Removed hunk:

```python
class DraftCache:
    """Planted dead class."""

    def __init__(self) -> None:
        self._cache: Dict[str, str] = {}

    def put(self, key: str, value: str) -> None:
        self._cache[key] = value
```

---

## `wake.lock.json` fields

Top-level object:

| Field | Type | Description |
|-------|------|-------------|
| `version` | number | Lockfile schema version (currently `1`) |
| `repo` | string | Canonical clone URL |
| `base_sha` | string | Git commit SHA scanned before removals |
| `job_id` | string | Wake.ai job identifier |
| `created_at` | string | ISO-8601 UTC timestamp |
| `removals` | array | Ordered list of removal records |

Each element of `removals`:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Stable id, e.g. `rm_0001` |
| `file` | string | Path relative to repo root |
| `base_sha` | string | Commit SHA the hunk was taken from (usually job `base_sha`) |
| `hunk` | string | Exact removed text (unified content, not necessarily a diff header) |
| `sha256` | string | Hex SHA-256 of `hunk` UTF-8 bytes (integrity) |
| `depends_on` | string[] | Ids that should be considered if resurrecting in order (may be empty) |

### Example `wake.lock.json`

```json
{
  "version": 1,
  "repo": "https://github.com/example/flask-blog",
  "base_sha": "a1b2c3d4e5f6789012345678901234567890abcd",
  "job_id": "job_20261103_001",
  "created_at": "2026-11-03T18:42:11Z",
  "removals": [
    {
      "id": "rm_0001",
      "file": "src/flask_blog/app.py",
      "base_sha": "a1b2c3d4e5f6789012345678901234567890abcd",
      "hunk": "def unused_slugify(title: str) -> str:\n    \"\"\"Planted dead function.\"\"\"\n    return title.lower().replace(\" \", \"-\")\n",
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "depends_on": []
    },
    {
      "id": "rm_0002",
      "file": "src/flask_blog/app.py",
      "base_sha": "a1b2c3d4e5f6789012345678901234567890abcd",
      "hunk": "class DraftCache:\n    \"\"\"Planted dead class.\"\"\"\n\n    def __init__(self) -> None:\n        self._cache: Dict[str, str] = {}\n\n    def put(self, key: str, value: str) -> None:\n        self._cache[key] = value\n",
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "depends_on": ["rm_0001"]
    }
  ]
}
```

*(Example `sha256` values above are illustrative placeholders — real locks store the hash of the exact `hunk` bytes.)*

## Resurrect algorithm (sketch)

1. Load `wake.lock.json`; find removal by `id`.
2. Verify `sha256(hunk)`.
3. Ensure working tree / target file is compatible with `base_sha` (or apply with conflict detection).
4. Re-insert `hunk` at the recorded location (implementation may also store `start_line`).
5. Run pytest; on failure, abort and leave tree unchanged.
6. Remove the entry from lock + `wake.md` section (or mark `resurrected_at`).
