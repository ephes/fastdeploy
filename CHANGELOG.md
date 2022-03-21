0.1.2 - 2022-03-21
===================

### Features
- use mixin to raise events after uow context manager exits
    - #9 issue by @ephes

### Refactoring
- increase coverage for adapters/filesystem.py
    - #22 issue by @ephes
- refactor command handlers
    - #18 issue by @ephes
- improve message bus dependency
    - #13 issue by @ephes
- use the same `get_user_by_name` function everywhere
    - #10 issue by @ephes
- use own message bus to sync services during deployment
    - #8 issue by @ephes
- fix repository method names
    - #6 issue by @ephes

### Fixes
- exception in `run_task` on long output
    - #24 issue by @ephes
- delete deployments and steps from frontend after service deleted event
    - #11 issue by @ephes

0.1.1 - 2022-02-29
==================

### Features
- add CHANGELOG.md
    - #3 - add CHANGELOG.md by @ephes

### Fixes
