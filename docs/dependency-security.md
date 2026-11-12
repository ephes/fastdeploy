# Dependency security

## November 2026 Python refresh

`scripts/audit_python.py` on the previous lock reported 29 advisories in five
packages on Python 3.13. On Python 3.10 it also reported PYSEC-2026-3458 for
ansible-core 2.17.14, which is only locked for 3.10:

| Package | Before | After | Advisories |
| --- | --- | --- | --- |
| dnspython | 2.8.0 | 2.9.2 | CVE-2026-114605 |
| filelock | 3.32.7 | 4.2.10 | CVE-2026-112907 to -112913, -112915, -112935, -112936, -112938, -112939, -112940 (13) |
| setuptools | 83.0.0 | 84.2.1 | GHSA-xmj3-9gf7-h52w |
| tornado | 6.5.9 | 6.6.1 | CVE-2026-115927, CVE-2026-116577, CVE-2026-116578 |
| virtualenv | 21.7.13 | 21.15.6 | CVE-2026-113714, -113715, -113717, -113718, -113720, -113722, -113723, -113725, -113726, -113732, -113776 (11) |
| ansible-core (3.10 only) | 2.17.14 | removed with 3.10 | PYSEC-2026-3458 |

dnspython is runtime exposure through FastAPI's email validation. filelock,
setuptools, Tornado and virtualenv come in through development, docs, notebook
and pre-commit chains; production installs them too, because the deploy runs
`uv sync --frozen` with the default groups.

The fixed dnspython (2.9.0+), filelock (4.2.1+) and Tornado (6.6+) releases
require Python 3.11+, and there is no patched 3.10 release of any of them.
Python 3.10 reached end of life in October 2026, and no FastDeploy deployment or
CI job uses it (production runs 3.14, CI 3.13). `requires-python` is therefore
`>=3.11`. Only these packages and the versions their resolver requires (distlib
0.4.4 and packaging 26.3 for virtualenv) were refreshed; the 3.10-only lock
forks (async-timeout, backports-asyncio-runner, exceptiongroup, tomli, ipython
8, resolvelib 1.0) are gone.

After the refresh, the audit reports no known vulnerabilities on Python 3.11
and 3.14.

## Gates

Run `python scripts/audit_python.py` under Python 3.11 and 3.14. The frozen
all-group/all-extra export is a separate checked process, so an export failure
cannot feed an empty audit. pip-audit 2.10.1 uses the selected interpreter to
evaluate markers. Synthetic subprocess tests cover export and audit failures,
call order and temporary-file cleanup. CI audits both interpreters and the full
npm lock independently on every push and on a weekly schedule, with read-only
permissions. Never ignore or suppress an advisory in these gates.
