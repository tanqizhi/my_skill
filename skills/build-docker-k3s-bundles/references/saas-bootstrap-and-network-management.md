# SaaS Bootstrap and Network Management

Read this reference when a bundle contains SaaS, requires resumable or reinstallable execution, exposes Docker or K3s services, or manages bundle-owned NAT rules.

## SaaS Bootstrap

For every enabled SaaS service, identify all required PaaS and external targets and the startup configuration that binds the service to them. Model dependencies by declared capability and provider rather than a closed list of products or middleware types.

Before generating an installable bundle, confirm whether the installer must initialize any dependency data, configuration, metadata, policy, identity, or other required state before SaaS starts. Model each task with:

- a stable task ID and owning SaaS service;
- a provider-neutral kind and a provider-specific operation; examples include database migrations, configuration-center entries, cache warm-up, message-broker topics, object-storage buckets, search indexes, identities, policies, certificates, and licenses, but the model must accept other types;
- source path and checksum;
- target dependency and non-secret target selector;
- prerequisites and execution order;
- idempotency method, such as a migration-history table, content hash, existence check, or safe upsert;
- backup and rollback behavior;
- post-import verification;
- the SaaS services blocked by failure.

Do not infer that dependency initialization is unnecessary merely because the target service is external or supplied by a layered package. Record an explicit required or skipped decision. A skipped task needs a reason and a verifiable precondition.

Before starting SaaS, render and validate its effective dependency configuration. Verify common connection data plus every provider-specific selector declared by the dependency adapter. Examples include a database or schema and a Nacos namespace/group/Data ID, but those examples must not constrain supported types. Test reachability and authentication only when authorized. Never print secret values.

The required order is:

1. validate or deploy target PaaS;
2. wait for the target readiness check;
3. back up affected dependency state when required;
4. execute declared bootstrap tasks in dependency order;
5. verify the imported state;
6. validate the effective SaaS dependency configuration;
7. start the dependent SaaS service;
8. run the SaaS health check.

Failure in steps 1 through 6 blocks the affected SaaS service. Record the failed task, observed target, rollback result, and resume command.

## Resumable Installation and Reinstall

Use an explicit stage graph rather than a single success marker. Each stage performs precheck, apply, verify, and atomic checkpoint recording.

Persist at least:

- bundle version and manifest fingerprint;
- stage ID, status, attempt count, start and finish time;
- relevant input fingerprint;
- observed outputs and verification result;
- affected services and nodes;
- backup or rollback metadata;
- redacted failure details and exact resume command.

Required installer modes:

- `--status`: display completed, failed, invalidated, skipped, and pending stages;
- `--resume`: continue from the first failed, invalidated, or incomplete stage;
- `--restart-from <stage>`: invalidate the selected stage and its downstream stages after confirmation;
- `--reinstall <service-or-stage>`: rerun the target and affected downstream stages while preserving data and user configuration;
- a separately named clean option for destructive reinstall, requiring backup and explicit confirmation;
- `--dry-run`: show planned stage and host changes where practical.

A changed input invalidates the stage that consumes it and downstream dependents, not unrelated completed work. Do not mark a stage complete until post-apply verification succeeds. A report-generation failure must not replace the original installation exit code.

## External Port Management

The management entrypoint must offer interactive list, add, update, delete, and verification operations.

For Docker:

- manage explicit host address, published port, container port, and protocol mappings;
- identify generated versus user-managed Compose or runtime configuration;
- detect host-port conflicts before applying;
- preview and back up the affected configuration;
- recreate only affected services and verify health;
- roll back configuration and service state on failure.

For K3s:

- manage the selected Service and its NodePort definitions;
- discover the cluster's effective NodePort range instead of assuming the default;
- detect conflicts across Services and protocols;
- preview and back up the affected manifest or live object;
- patch only the intended Service and verify endpoints and reachability;
- roll back to the captured object on failure.

Port exposure does not by itself authorize host firewall or NAT changes. Treat those as a separate confirmed action.

## NAT Terminology and Ownership

Use precise terms:

- `nat` is the iptables table;
- `PREROUTING` is a built-in chain;
- the bundle-specific named object is a user-defined chain.

Manage only a verified bundle-owned user-defined chain and the jump that connects it to `nat/PREROUTING`. Prefer a stable comment or another ownership marker, a manifest record, and a saved rule fingerprint. Never modify Docker, K3s, CNI, firewalld, or unrelated user-managed rules merely because they are nearby.

PREROUTING DNAT controls address translation, not access authorization. If source allow or deny behavior is required, model the applicable INPUT or FORWARD behavior separately and request confirmation rather than pretending DNAT is a filter rule.

## Existing Chain Discovery and Reuse

When modifying a bundle, inspect existing installation, management, uninstall, persistence, and systemd code for:

- `iptables -t nat -N`, `-A`, `-I`, `-R`, `-D`, and `-F`;
- PREROUTING jumps;
- `iptables-save` and `iptables-restore`;
- nftables tables, chains, hooks, and rules;
- firewalld direct or rich rules;
- reboot-persistence services and files.

Extract the existing chain name, parent jump, position, comments, rule shape, persistence mechanism, and cleanup behavior. Reuse the exact existing chain name and placement only when its ownership and purpose are compatible with the bundle. If there are multiple candidates, ambiguous ownership, or incompatible contents, stop and ask; do not create an additional chain as a workaround.

The installer must repeat discovery on every target node before applying. Handle observed state idempotently:

- compatible chain, jump, and rules exist: adopt and verify them;
- compatible chain exists but owned entries are missing: add only the missing entries;
- expected jump exists more than once: stop and report duplicates before modifying;
- same-name chain exists with ambiguous or incompatible rules: stop and request a decision;
- no compatible chain exists: create one only after the host-change confirmation already required by the workflow.

Never blindly run a create-chain command or append a PREROUTING jump.

## Interactive NAT CRUD

The management entrypoint must support:

- `firewall list`: show rule ID, current position, match, destination, counters, source, and persistence state;
- `firewall add`: insert at the beginning, end, before a rule ID, or after a rule ID;
- `firewall update`: replace a selected owned rule while retaining a stable identity;
- `firewall delete`: remove a selected owned rule after showing its effect;
- `firewall status`: show backend, table, parent chain, owned chain, jump position, node state, and drift;
- `firewall sync`: reconcile the manifest's desired rules to the target nodes;
- `firewall repair`: repair missing owned jumps or rules without touching foreign rules.

Before mutation, show the target nodes, exact ordered diff, commands or equivalent operations, and persistence effect. Obtain authorization, snapshot the current relevant rules, apply using the safest atomic mechanism supported by the detected backend, verify, and retain rollback data.

## Cluster Synchronization and Node Failure

When the deployment is a cluster, synchronize the desired bundle-owned NAT chain, jump, order, and rules to every declared server and agent node. Do not assume rules propagated from one node. Use the node inventory as the source of truth and retain node name, IP address, role, backend, observed chain, desired fingerprint, and applied fingerprint.

Perform read-only preflight on all nodes before the first mutation. Snapshot each reachable node before changing it. Apply and verify per node, then compare the desired rule fingerprint across the cluster.

If any node fails:

1. stop before silently declaring cluster success;
2. display the failed node's name and IP address;
3. display the redacted failure reason;
4. display one exact, copy-ready command that an operator can run locally on that node, for example `cd <installed-bundle-dir> && sudo ./manage.sh firewall sync --local-node --non-interactive`;
5. ask the user to choose `continue` or `rollback`;
6. on `continue`, retain the failure, manual command, and partial state, then continue with remaining nodes;
7. on `rollback`, restore the snapshots on every node changed by the current operation and report any rollback failure.

The generated command must use the actual installed bundle directory and the failed node's intended configuration; placeholders are not acceptable in the runtime prompt. The command must not contain credentials.

In non-interactive mode, stop on node failure unless the caller explicitly supplies `--on-node-failure continue` or `--on-node-failure rollback`. Never default to continue. A later `firewall sync` or `firewall repair` must reconcile failed, unavailable, or newly joined nodes.

## Validation and Reporting

Validate at least:

- SaaS bootstrap required and skipped paths;
- provider-neutral bootstrap behavior plus representative provider-specific idempotency and failure blocking;
- dependency configuration mismatch and unreachable-target handling;
- interruption and resume at representative stages;
- repeated installation without duplicate work;
- data-preserving reinstall and explicitly confirmed clean reinstall;
- Docker port and K3s NodePort CRUD, conflicts, verification, and rollback;
- discovery and reuse of an existing compatible chain;
- same-name incompatible-chain refusal;
- repeated NAT application without duplicate chains, jumps, or rules;
- rule insertion, replacement, deletion, ordering, persistence, and rollback;
- all-node synchronization, drift detection, newly joined node repair, and unavailable nodes;
- interactive continue and rollback choices after a node failure;
- exact node name, IP address, and local recovery command in the prompt and report.

The deployment and operations report must record bootstrap decisions and results, SaaS dependency checks, latest checkpoint, resume or reinstall activity, external ports, NAT backend and chain ownership, reused or created state, PREROUTING jump position, per-node fingerprints and results, user continue-or-rollback decisions, manual recovery commands, persistence status, and remaining drift. Redact secrets.
