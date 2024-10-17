# Command Line Interface

The command line interface can be used to interact with the application.

# Usage

```shell
Usage: commands.py [OPTIONS] COMMAND [ARGS]...

Options:
  --install-completion [bash|zsh|fish|powershell|pwsh]
                                  Install completion for the specified
                                  shell.
  --show-completion [bash|zsh|fish|powershell|pwsh]
                                  Show completion for the specified shell,
                                  to copy it or customize the installation.
  --help                          Show this message and exit.

Commands:
  coverage      Run and show coverage.
  createuser    Create a new user. Username and password are either set via
                environment variables, to create an initial user via ansible
                for example, or interactively via the command line.
  deploy-production   Deploy to production environment.
  deploy-staging      Deploy to staging environment.
  docs          default: mkdocs serve --build: clean, openapi and...
  docs-build    build mkdocs
  docs-clean    Delete the site_path directory recursively.
  docs-openapi  load new openapi.json into mkdocs
  docs-serve    serve mkdocs
  jupyterlab    Start a jupyterlab server.
  notebook      Start the notebook server.
  run           Run the API server.
  serve         = run (start the devserver)
  syncservices  Sync services from filesystem with services in database.
  test          Run the tests: - run backend tests via pytest - fun...
  up            = run (start the devserver)
  update        Update the development environment by calling: -...
```

# Commands In Detail

## syncservices

This command syncs the services from the filesystem with the services in the
database. If a service is in the filesystem but not in the database, it will be
added to the database and if it's in the database but not in the filesystem, it
will be removed.

This command does not take any arguments.

    ```shell
    $ commands.py syncservices
    ```
