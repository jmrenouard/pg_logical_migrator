# Project Documentation Hub

Welcome to the technical documentation for the `pg_logical_migrator` project. This documentation is split into thematic units to cover every aspect of PostgreSQL logical replication and the usage of this tool.

## Technical Documentation Index

- **[Core Concepts](CONCEPTS.md)**: Introduction to the publish-subscribe architecture and replication objects.
- **[Configuration Guide](CONFIGURATION.md)**: Prerequisites and required PostgreSQL parameters for source and destination.
- **[Tools & Usage Guide](TOOLS.md)**: CLI flags, Makefile targets, TUI walkthrough, automated mode, and output artifacts.
- **[Docker Guide](DOCKER.md)**: Building and running the application within an isolated Docker container.
- **[Detailed Workflow](WORKFLOW.md)**: A deep dive into the 14-step automated sequence orchestrated by the tool.
- **[Migration Lifecycle](LIFECYCLE.md)**: Summary of actions and phases from preparation to final cleanup.
- **[Execution Validation](VALIDATION.md)**: Critical control points and a schema verification checklist.
- **[Limitations & Pitfalls](LIMITATIONS.md)**: Detailed constraints, unsupported objects, and the row identification problem.

---

## Project Specifications & Management

For internal project specs, roadmaps, and progress tracking, please refer to the **[PROJECT/](../PROJECT/)** directory.

- [Specifications](../PROJECT/SPECIFICATIONS.md)
- [Milestones](../PROJECT/MILESTONES.md)
- [Constitution](../PROJECT/CONSTITUTION.md)
- [Progress Tracking](../PROJECT/PROGRESS.md)
