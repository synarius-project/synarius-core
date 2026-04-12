# Contributing to Synarius

Thank you for your interest in contributing to Synarius!

Synarius is a Python-first platform for graphical system modeling and simulation.
We welcome contributions of all kinds, including code, documentation, bug reports, and ideas.

## Ways to Contribute

You can contribute by:

- Reporting bugs
- Suggesting features
- Improving documentation
- Submitting code changes

## Getting Started

1. Fork the repository
2. Create a feature branch:

   ```bash
   git checkout -b feature/my-feature
   ```

3. Use a **virtual environment** and install **synarius-core** in editable mode with the same `python` you use for tests and tooling (see **[README.md](README.md)**). Optional extras (e.g. `[timeseries]`, `[fmu]`) belong in that same environment.

4. Make your changes
5. Run tests:

   ```bash
   pytest
   ```

6. Open a Pull Request

## Development Guidelines

**Canonical programming guidelines** (Python 3.11, repository boundaries, code style, testing, pull requests) are maintained in the **[Synarius programming guidelines](https://synarius-project.github.io/synarius-guidelines/programming_guidelines.html)** (Sphinx documentation built from [synarius-guidelines](https://github.com/synarius-project/synarius-guidelines)). Follow that document first; the sections below only add repository-specific reminders.

### Architecture

Synarius is split into separate repositories:

- **synarius-core**: simulation engine and GUI-less backend (no PySide/Qt dependency).
- **synarius-apps**: DataViewer, ParaWiz, and shared Qt tools — depends on core; usable **without** Synarius Studio.
- **synarius-studio**: graphical modeling and simulation IDE (PySide6).

**Important:**

- Core must remain independent from the GUI and from Studio.
- All simulation logic belongs in synarius-core.

### Testing

- All new features should include tests
- Bug fixes must include a regression test if possible
- Run tests before submitting a PR

### Pull Request Guidelines

- Keep PRs small and focused
- Provide a clear description of changes
- Reference related issues
- Ensure CI is passing

## Contributor License Agreement (CLA)

By submitting a contribution, you agree to the Synarius CLA.

Contributions cannot be merged without accepting the CLA.

See [CLA.md](CLA.md) for details and links.

## Communication

- Use GitHub Issues for bugs and feature requests
- Use GitHub Discussions for questions and ideas

Please follow the Code of Conduct in all interactions.

## Questions?

If you're unsure about anything, feel free to open an issue or discussion.

We're happy to help!
