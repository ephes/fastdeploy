# fastDeploy

## project installation for development

1. Create a venv & activate it.

2. Install dev requirements via `pip-tools`

    python -m pip install pip-tools

    # Add/Remove dependencies to develop.in/production.in
    pip-compile .\app\requirements\develop.in
    pip-compile .\app\requirements\production.in

    # Sync (install) prod|dev to the activated venv.
    pip-sync .\app\requirements\develop|production.txt
