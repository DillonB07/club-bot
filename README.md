# Python Template

This is a template for Python projects. It includes everything needed for a project.

## Requirements

- [Python](htt[s://python.org]) 3.10 or higher
- [Poetry](https://python-poetry.org/)

## Setup

1. Clone this repository
2. Run `poetry install --group dev` to install all dependencies
3. Run `poetry run sourcery login` to login to Sourcery and enable the Sourcery pre-commit hook
4. Run `poetry run pre-commit install` to install the pre-commit hooks
5. Run `poetry run pre-commit run --all-files` to run the pre-commit hooks on all files

## Hooks

There are a variety of pre-commit hooks that are run on each commit. These include:

- Black. This is a code formatter that formats the code to a standard format.
- Ruff. This is a linter that checks the code for errors.
- Sourcery. This is a code refactoring tool that refactors code that can be improved.

If any of the hooks fail to run, the commit will be aborted. You can run the hooks manually by running `poetry run pre-commit run --all-files`.

## Contributions

Contributions are welcome. Please open an issue or pull request if you have any suggestions or improvements.

Pull requests should be made to the `develop` branch. Pull requests to `main` will be rejected.

Before committing, please make sure to run the pre-commit hooks which can be installed with `poetry run pre-commit install`. You can run them manually by running `poetry run pre-commit run --all-files`.
