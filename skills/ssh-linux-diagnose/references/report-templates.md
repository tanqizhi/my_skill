# Report Templates

Use these templates to keep diagnosis reproducible and easy to hand off.

## Pre-Diagnosis Interview

```markdown
Before I connect or prepare server commands, I need a few facts:

- Target host and access path:
- Symptom:
- Start time and pattern:
- Impact scope:
- Recent changes:
- Already tried:
- Production or non-production:
- Allowed sudo:
- Forbidden actions:
- Desired outcome:
```

## Stage Assessment

```markdown
## Current Assessment
- Conclusion:
- Confidence: high / medium / low
- Impact:
- Needs change: no / requires confirmation

## Evidence
- Observed facts:
- Files involved:
- Key command output summary:
- Human-repeatable evidence commands:
- Timeline clues:

## Ruled Out
- Hypothesis:
- Reason:

## Next Step
- Read-only checks:
- Changes requiring confirmation:
```

## Final Report

```markdown
## Final Conclusion
- Root cause or most likely cause:
- Confidence:
- Impact:

## Evidence Chain
- Core evidence:
- Files involved:
- Human-repeatable evidence commands:
- Timeline:
- Evidence gaps:

## Commands
- Executed by Codex:
- Executed manually by user:
- Suggested but not executed:

## Remediation
- Recommended changes:
- Risks:
- Rollback or recovery:
- Post-change verification:

## Follow-Up
- Monitoring:
- Preventive actions:
```

## Vulnerability Verification Report

```markdown
## Vulnerability Assessment
- Vulnerability:
- Component:
- Target host:
- Result: confirmed affected / suspected affected / no affected evidence found / likely false positive / unable to verify
- Confidence:

## Verification Evidence
- Installed or running version:
- Exposure path:
- Config or mitigation state:
- Scanner/advisory evidence:
- Files involved:
- Human-repeatable evidence commands:

## Remediation Status
- Change needed:
- Confirmation required:
- Post-fix verification commands:
```

## Manual Execution Prompt

```markdown
I cannot directly reach this intranet host, so please run this reviewed command manually.

Target host:
Command:
Purpose:
Safety review:
Expected output:

Paste the full output here, including errors.
```
