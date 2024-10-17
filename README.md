# fastDeploy

## Installation for development

### Create a venv & activate it and install the dev requirements
```shell
     uv venv -p python3.12
     source .venv/bin/activate.fish
     uv sync
```

### Set up the database
```shell
    initdb databases/postgres
    postgres -D databases/postgres  # in a different terminal tab
    createdb deploy
    createuser deploy
    python commands.py createuser  # will also create the tables

    # Create a test database and copy the schema over
    createdb deploy_test
    pg_dump deploy | psql deploy_test
```

### Run the tests
```shell
    pytest
```

### Run the static type checker
```shell
    mypy deploy
```

### Run the devserver
```shell
    honcho start
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

## Just To Trigger Deploy
