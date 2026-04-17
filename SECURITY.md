# Security Policy

## Supported Versions

We actively provide security updates for the following versions of **pg_logical_migrator**:

| Version | Supported          |
| ------- | ------------------ |
| 1.3.x   | :white_check_mark: |
| < 1.3.0 | :x:                |

## Reporting a Vulnerability

**Do not open a GitHub issue for security vulnerabilities.**

If you discover a security vulnerability within this project, please report it privately to the maintainers. You can contact us via:

- Email: [jmrenouard@gmail.com](mailto:jmrenouard@gmail.com)

Please include the following information in your report:
- A description of the vulnerability.
- Steps to reproduce the issue.
- Potential impact of the vulnerability.
- Any suggested fixes.

We will acknowledge receipt of your report within 48 hours and provide a timeline for a fix if necessary.

## Best Practices for Users

Since **pg_logical_migrator** handles database credentials and sensitive data:

1.  **Credential Safety**: Never commit your `config_migrator.ini` file to version control. It is already included in `.gitignore`.
2.  **Encryption**: Always use encrypted connections (SSL/TLS) when migrating databases over untrusted networks.
3.  **Least Privilege**: Use database users with the minimum required permissions for the migration process.
4.  **Audit Logs**: Review the HTML reports generated in the `RESULTS/` directory for any unexpected command executions.

Thank you for helping keep **pg_logical_migrator** secure!
