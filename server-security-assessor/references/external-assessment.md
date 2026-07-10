# External assessment

Use this workflow only for External or Both modes. Read `scope-policy.md` first and pass the frozen request to the command-plan helper. Review every generated argv array before executing it through Codex.

## No existing report

1. Run bounded Nmap discovery against supplied hosts only. Use explicit ports for targeted coverage and TCP `-p-` only for full coverage. Use conservative timing, retry, and host-timeout settings.
2. Feed in-scope URLs or services to Nuclei. Write JSONL, use conservative rate and concurrency, and omit cloud/dashboard upload flags.
3. Identify Web services from an in-scope URL or matching Nmap result.
4. Offer Chaitin Xray only for those Web services. Use active crawling for full Web coverage and exact URL mode for targeted coverage.
5. Normalize outputs and select findings for optional safe PoC validation.

## Existing report

Do not run broad discovery. Verify only imported report rows and exact assets. Nuclei templates and Xray plugins must correspond to the reported issue. Disable Xray crawling; use exact URL mode.

## Safe PoC boundary

Ask once whether bounded safe PoCs are allowed, then review each proposed PoC. Permit only checks that are non-destructive, non-persistent, rate-limited, and avoid material state changes or sensitive-data extraction. Block brute force, credential attacks, denial of service, unsafe fuzzing, file writes, command execution that changes the target, and out-of-band callbacks without separate confirmation.

If safe verification is impossible, preserve the finding as `probable` or `not-assessable` and describe the missing evidence.

## Stop conditions

Stop immediately on scope drift, redirect to an unlisted origin, health degradation, unusual error rates, tool output corruption, or user cancellation. Preserve partial outputs and coverage gaps.

Write Nmap XML, Nuclei JSONL, and Xray JSON into the run evidence directory. Treat a missing Xray JSON file as no findings only when the command exit code and log show successful completion.

