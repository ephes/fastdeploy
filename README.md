# fastDeploy

## Installation for development

1. Create a venv & activate it.

2. Install dev requirements via `pip-tools`.

    ```
    python -m pip install pip-tools

    # Add/Remove dependencies to develop.in/production.in
    pip-compile .\app\requirements\develop.in
    pip-compile .\app\requirements\production.in

    # Sync (install) prod|dev to the activated venv.
    pip-sync .\app\requirements\develop|production.txt
    ```



## Documentation

This project uses [mkdocs.org](https://www.mkdocs.org) with [material theme](https://squidfunk.github.io/mkdocs-material/) for documentation.  
To add an updated `openapi.json` to the docs run `python commands.py docs --openapi`.  

Layout:

    mkdocs.yml        # The configuration file.
    docs/
        index.md      # The documentation home.
        openapi.json  # Downloaded from the FastAPI devserver. Use the plugin with `!!swagger openapi.json!!`
        ...           # Other markdown pages, images and other files.
