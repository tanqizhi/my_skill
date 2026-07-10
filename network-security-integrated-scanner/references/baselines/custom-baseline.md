# Custom baseline rules

Accept user-provided compliance, industry, or internal checklists only after mapping each rule to:

- a unique rule ID and title;
- applicable platforms, services, and scope;
- a read-only evidence method;
- expected and failing conditions;
- severity and rationale;
- remediation and retest guidance.

Reject a rule that requires an out-of-scope asset, destructive action, target-side installation, or ambiguous pass/fail condition. Keep the user's rule ID in `baseline_mappings`. Run default and custom baselines together unless the user explicitly asks to replace the default.

