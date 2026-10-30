# Security Review Skill

Security reviews and secure-by-default guidance for code.

## Workflow

1. Identify ALL languages and ALL frameworks in the project (frontend and backend)
2. Think about well-known security best practices for each language/framework
3. Operate in one of these modes:
   - **Default**: Write secure code from the start
   - **Passive**: Flag critical vulnerabilities while working
   - **Report**: Produce a full security report when asked

## Report Format (when requested)

Write findings to `security_best_practices_report.md` with:
- Executive summary at the top
- Sections by severity (Critical first)
- Each finding with a numeric ID, location (file + line numbers), and impact statement
- Critical findings include a one-sentence impact statement

## Fixes

- Fix one finding at a time
- Add clear comments explaining the security best practice
- Consider regressions — don't break the project
- Follow the project's normal commit/change workflow

## General Security Advice

- **No incrementing IDs for public resources**: Use UUID4 or random hex strings
- **No hardcoded secrets**: API keys, passwords, tokens must use environment variables
- **Validate all input**: Sanitize user input to prevent injection attacks
- **Principle of least privilege**: Limit permissions, don't run as root/admin
- **Dependencies**: Check for known vulnerable packages
- **Error handling**: Don't leak stack traces or internal paths to users
