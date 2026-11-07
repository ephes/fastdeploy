# November dependency security refresh (pending)

This branch is not merge-ready: the full Python 3.10 lock audit remains red.
The supported Python range is unchanged. No deploy, tag or release is part of this work.

## Python graph

Python 3.13: 29 baseline advisories in five packages; refreshed graph: zero.
dnspython is runtime exposure through FastAPI email validation; filelock,
setuptools, Tornado and virtualenv are development/docs/notebook/pre-commit chains.
Refresh only these packages and their resolver-required dependencies.

| Package | Baseline | Refreshed on 3.13 | Exact baseline advisory IDs |
| --- | --- | --- | --- |
| dnspython | 2.8.0 | 2.9.2 | CVE-2026-114605 |
| filelock | 3.32.7 | 4.2.9 | CVE-2026-112940, CVE-2026-112913, CVE-2026-112907, CVE-2026-112938, CVE-2026-112936, CVE-2026-112910, CVE-2026-112909, CVE-2026-112911, CVE-2026-112939, CVE-2026-112915, CVE-2026-112935, CVE-2026-112912, CVE-2026-112908 |
| setuptools | 83.0.0 | 84.2.1 | GHSA-xmj3-9gf7-h52w |
| tornado | 6.5.9 | 6.6 | CVE-2026-116577, CVE-2026-115927, CVE-2026-116578 |
| virtualenv | 21.7.13 | 21.15.6 | CVE-2026-113726, CVE-2026-113776, CVE-2026-113732, CVE-2026-113725, CVE-2026-113722, CVE-2026-113714, CVE-2026-113723, CVE-2026-113715, CVE-2026-113720, CVE-2026-113717, CVE-2026-113718 |

The universal lock retains baseline versions of filelock (3.32.7), virtualenv
(21.7.13), Tornado (6.5.9) and dnspython (2.8.0) on Python 3.10. Explicit
marker-scoped constraints prevent the refresh from introducing new 3.10
advisories. setuptools is fixed on both interpreter branches. The 3.10 audit
therefore drops from 29 to 28 advisories in four packages, and remains red:

- dnspython 2.8.0: CVE-2026-114605
- filelock 3.32.7: CVE-2026-112940, CVE-2026-112913, CVE-2026-112907, CVE-2026-112938, CVE-2026-112936, CVE-2026-112910, CVE-2026-112909, CVE-2026-112911, CVE-2026-112939, CVE-2026-112915, CVE-2026-112935, CVE-2026-112912, CVE-2026-112908
- tornado 6.5.9: CVE-2026-116577, CVE-2026-115927, CVE-2026-116578
- virtualenv 21.7.13: CVE-2026-113726, CVE-2026-113776, CVE-2026-113732, CVE-2026-113725, CVE-2026-113722, CVE-2026-113714, CVE-2026-113723, CVE-2026-113715, CVE-2026-113720, CVE-2026-113717, CVE-2026-113718

dnspython >=2.9.0, filelock >=4.2.1 and Tornado >=6.6 require Python >=3.11.
The resolver also cannot select fixed virtualenv with the 3.10-compatible
filelock branch. Dropping 3.10 or changing runtime dependency features needs
a separate explicit decision; this change does neither.

## Unblocking this branch

When Python 3.10-compatible patched releases become available, remove or relax
all three marker-scoped `constraint-dependencies` in `pyproject.toml`, refresh
the affected chains with `uv lock --upgrade-package <name>`, and rerun the frozen
audits under Python 3.10 and 3.13. Exact baseline pins deliberately prevent an
unreviewed resolver change; they will not pick up backports automatically.
Both audits must reach zero before this branch can be considered for merge.
Alternatively, revise Python support only through an explicitly approved change.
Rerun the application checks and review the completed repair before merging.

## Gates and regression evidence

Run `python scripts/audit_python.py` under both 3.10 and 3.13. The frozen
all-group/all-extra export is a separate checked process, so an export failure
cannot feed an empty audit. pip-audit 2.10.1 uses the selected interpreter to
evaluate markers. Synthetic subprocess tests cover export/audit failures,
call order and temporary-file cleanup. CI audits both interpreters and the
full npm lock independently on push and weekly schedule, with read-only permissions.

The original Python 3.13 lock and frontend lock fail their real audits; the
refreshed 3.13 lock and repaired frontend lock pass. This is advisory regression
evidence, not a claim that all supported Python graphs are fixed.

Local lint/types/docs pass. Database tests require isolated PostgreSQL; local
initialization failed with shared-memory exhaustion. Chromium launch was denied
by the sandbox. Branch CI must execute these checks before any future merge.
