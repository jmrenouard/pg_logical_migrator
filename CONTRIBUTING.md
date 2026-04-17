# Contributing to pg_logical_migrator

Thank you for your interest in contributing to **pg_logical_migrator**! We welcome contributions from the community to help improve this tool.

## How to Contribute

### 1. Report Bugs
- Use the **Bug Report** template to describe the issue.
- Include steps to reproduce the bug and details about your environment (OS, PostgreSQL version, Python version).

### 2. Suggest Features
- Use the **Feature Request** template.
- Explain why the feature would be useful and how it should work.

### 3. Submit Pull Requests
1. Fork the repository.
2. Create a new branch for your feature or fix (`git checkout -b feature/my-new-feature`).
3. Ensure your code follows the project's style and includes tests.
4. Run tests to make sure everything is working:
   ```bash
   make test
   ```
5. Commit your changes and push to your fork.
6. Open a Pull Request with a clear description of the changes.

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/jmrenouard/pg_logical_migrator.git
   cd pg_logical_migrator
   ```
2. Set up a virtual environment and install dependencies:
   ```bash
   make venv
   source venv/bin/activate
   ```
3. Run the test environment (requires Docker):
   ```bash
   cd test_env
   ./setup_pagila.sh
   ```

## Code of Conduct

Please be respectful and professional in all interactions within the project.

---

Thank you for making **pg_logical_migrator** better!
