# Default assessment baseline

Apply these sources by default:

- CIS Level 1 concepts appropriate to the detected Linux family and deployed services.
- Current vendor security guidance for the operating system and identified products.
- CVE severity plus actual exposure, prerequisites, exploitability, and compensating controls.
- External-to-internal evidence: listening interface, owning process, installed package, effective configuration, and relevant logs.

Do not mark a version as vulnerable solely because a banner appears old; account for vendor backports and verify package advisories when possible. Record the exact baseline label and source used by each finding. Treat unsupported or unverifiable controls as coverage gaps.

