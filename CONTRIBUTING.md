# Contributing to The Show

## Filing issues

Use [GitHub Issues](https://github.com/markscleary/the-show/issues). Include the OS and Python version, a minimal programme YAML that reproduces the problem, and the full error output or unexpected behaviour.

## Proposing changes

Open an issue first for anything beyond a small bug fix or documentation correction. For code changes: fork the repo, work on a branch named for the issue or feature, ensure `pytest tests/` passes with 231 tests before opening a pull request. The test suite includes timing-sensitive urgent-contact tests — run them in a clean environment.

For changes to the executor, loader or dispatcher: add or update tests. Changes that reduce test coverage will not be merged.

## Code of conduct

Treat contributors with the same respect you would want on a professional production. Disagreements about design are welcome — disrespect is not. Short+Sweet runs festivals across twenty-seven cities; the same standard applies here.

Questions: open an issue or contact [mark@shortandsweet.org](mailto:mark@shortandsweet.org).
