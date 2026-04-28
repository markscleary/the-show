# Contributing to The Show

The Show is open source under the MIT licence. Contributions are welcome — but the project has scope discipline that's worth understanding before you write code.

## What The Show is for

The Show is a programme runtime for creative work. Festivals, broadcasts, live events, anything that has a programme and a running order. The theatrical metaphor is not decoration — it's what makes the runtime legible to creative operators who don't think in graph theory.

The Show is not for code agents. Not enterprise automation. Not SaaS. Not compliance tooling. Other runtimes already do those things well.

If your contribution moves The Show toward those territories — multi-tenant deployment, RBAC at the runtime level, compliance dashboards — it's likely not the right fit. Open an issue first to discuss before writing code. We may suggest a different home for the idea.

## How to contribute

### Bug reports

Use the bug report template. Include the version, the programme, and the logs. Minimal reproductions get fixed faster than vague descriptions.

### Feature requests

Use the feature request template. Describe the use case before the solution. Concrete examples beat abstract descriptions. The Show is small on purpose — features earn their way in by serving a real creative-work use case.

### Pull requests

Small focused PRs are easier to review than large ones. One change per PR. Tests for the change. Documentation updated if behaviour changes.

For anything non-trivial, open an issue first. We'd rather discuss the design before you write the code than ask you to rewrite it during review.

## Development setup

```
git clone https://github.com/markscleary/the-show
cd the-show
python3.11 -m venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

CI runs the test suite on every push and pull request. PRs need green CI before merge.

## Style

- Code: ruff and black config in `pyproject.toml`. CI enforces.
- Tests: pytest. Tests for behaviour, not implementation. Aim for clarity over cleverness.
- Docs: written in plain prose. The operator guide uses the theatrical metaphor consistently — Director, Stage Manager, House Manager, scenes, programmes. Maintain it.
- Commits: present tense, short summary, more detail in the body if needed. Reference issue numbers in the body.

## Code review

Pull requests are reviewed by maintainers. We may ask for changes. We may say no — usually because the proposal doesn't fit the runtime's scope, occasionally because the implementation needs rework. Either way, we'll explain why.

## Releases

The Show follows semver. v1.x is stable. Breaking changes wait for v2.

## Maintainers

- Mark Cleary, Short+Sweet International — project lead
- Open to additional maintainers as the project grows

## Licence

MIT. See LICENSE.

## Code of conduct

Be useful, be kind, don't be a jerk. Disagreement is fine; cruelty isn't. Maintainers reserve the right to remove comments, lock issues, or block contributors who can't meet that bar.

This isn't a long document because it doesn't need to be one. The bar is plain decency.
