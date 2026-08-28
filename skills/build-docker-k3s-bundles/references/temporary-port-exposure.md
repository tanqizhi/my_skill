# Temporary Port Exposure

Use this contract when generating or modifying `manage.sh`. It covers ad hoc access such as temporarily exposing the `nacos` service on `0.0.0.0:8848` without turning that endpoint into permanent bundle configuration.

## Operator Interface

Provide the same capability through an interactive menu and commands suitable for automation.

Minimum non-interactive interface:

```text
./manage.sh expose add <service-or-container> <listen-endpoint> [<target-port>[/<protocol>]] [--ttl <duration>] [--persistent]
./manage.sh expose list
./manage.sh expose status [<exposure-id>]
./manage.sh expose remove <exposure-id>
./manage.sh expose cleanup
```

Examples:

```text
./manage.sh expose add nacos 0.0.0.0:8848
./manage.sh expose add nacos 127.0.0.1:18848 8848/tcp --ttl 30m
./manage.sh expose remove exp-nacos-8848-tcp
```

`expose add nacos 0.0.0.0:8848` means: resolve the runtime object owned by service `nacos`, infer its target port only when the manifest makes that choice unambiguous, listen on every IPv4 interface on host port `8848`, and use TCP unless the declared service port specifies another protocol. Do not treat the listen port as proof that the target port is identical.

The interactive flow must ask for, or display and confirm, these fields:

- service or container
- host listen address and port
- target container, pod, or service port
- protocol
- temporary lifetime or persistent mode
- runtime adapter
- security scope and rollback command

## Parsing And Resolution

- Accept IPv4 endpoints such as `0.0.0.0:8848` and bracketed IPv6 endpoints such as `[::]:8848`. Reject ambiguous unbracketed IPv6 input.
- Validate addresses, ports from `1` through `65535`, supported protocols, duration syntax, and unknown options before changing state.
- Resolve a logical service name through the bundle manifest and deployment adapter. Do not rely only on a mutable container name, pod name, or current IP address.
- Infer the target port only when there is exactly one valid candidate or one declared port has an exact name or mapping that makes the choice deterministic. Otherwise stop and request `<target-port>/<protocol>`.
- Check host-listener conflicts across the requested address family and wildcard semantics. A listener on `0.0.0.0:8848` conflicts with another IPv4 listener on port `8848`, including one bound to a specific IPv4 address.
- Check for an equivalent existing bundle-owned exposure and return its ID idempotently instead of creating a duplicate.

## Lifecycle Semantics

Temporary is the default. A temporary exposure:

- is recorded as an atomic bundle-owned lease in management state
- survives the `manage.sh` process exiting so the operator can use it
- lasts until explicit removal, TTL expiry, runtime loss, or host reboot
- is not automatically restored after reboot, reinstall, upgrade, or workload reconciliation
- can be rediscovered and marked `active`, `expired`, `stale`, or `conflicted`
- is removed idempotently without touching unrelated listeners, firewall rules, containers, pods, or services

`--ttl` schedules or records an expiry and must be enforced by a bundle-owned mechanism that remains effective after `manage.sh` exits. If the bundle cannot provide reliable TTL enforcement on the target host, reject `--ttl` with an actionable explanation instead of pretending it is enforced.

`--persistent` is an explicit opt-in. Route it through the bundle's persistent exposure adapter and local desired-state mechanism, with backup and rollback. Never silently promote a temporary lease to persistent configuration.

On install, reinstall, upgrade, resume, or uninstall, inspect temporary leases and report them. Do not restore temporary leases automatically. Uninstall may remove active verified bundle-owned forwarding resources, but data-preserving uninstall must retain the audit record unless the operator explicitly purges state.

## Runtime Adapters

Select the adapter from observed runtime capabilities and the requested semantics. Record the selected adapter in the lease.

### Docker And Docker Compose

- Native Docker `--publish` or Compose `ports` generally requires container creation or recreation. Use it for persistent exposure or when the operator explicitly accepts recreation.
- For temporary exposure of an already-running container, prefer a bundle-supplied and verified host-forwarding adapter that does not recreate the application container.
- Resolve the current target through Docker metadata at creation and verification time. Do not persist a container IP as the sole identity.
- If forwarding depends on a helper binary, helper container, service manager, or firewall backend, include and verify that dependency in online and offline bundles. Do not assume tools such as `socat` are installed.

### K3s

- Use NodePort or another declared Service type for persistent exposure when its address and port constraints satisfy the request.
- NodePort alone cannot guarantee an arbitrary exact endpoint such as `0.0.0.0:8848`. For a temporary exact host listener, use a supervised, bundle-owned forwarding process derived from the resolved Service or workload, such as a managed `kubectl port-forward --address` adapter when supported.
- Track the selected workload dynamically and fail closed if the service has no ready endpoint. Do not pin an ephemeral pod name without a reconciliation or stale-state strategy.
- In multi-node bundles, require the operator to choose the node or an explicit node set. Do not expose every node by default.

### Firewall Or NAT

- Reuse the verified bundle-owned firewall or NAT chain when forwarding requires firewall rules.
- Never insert temporary rules into Docker, K3s, CNI, or unrelated user chains.
- Store exact ownership markers and rollback metadata before activation. Removal must match ownership metadata, not merely address and port text.

## Security And Confirmation

Treat wildcard and non-loopback addresses as externally reachable unless verified otherwise.

Before `expose add`, preview:

- resolved service and runtime object
- listen endpoint, target endpoint, and protocol
- selected node for K3s
- selected adapter and whether workload recreation is required
- current firewall state and any proposed owned rule
- lifetime, exposure ID, state path, verification steps, and rollback command

Interactive use requires confirmation for non-loopback listening. Non-interactive use requires both the normal approval flag and a dedicated acknowledgement such as `--accept-public-exposure`; do not let a generic `--yes` alone authorize `0.0.0.0`, `[::]`, or a non-loopback address.

Do not print credentials, tokens, resolved secrets, or sensitive environment values in previews, state, logs, or reports.

## State, Verification, And Recovery

Each lease record must contain at least:

- stable exposure ID and bundle ownership identity
- logical service name and resolved runtime kind
- listen address, host port, target port, and protocol
- runtime adapter, node or host, and creation timestamp
- TTL or persistence mode
- adapter resource identifiers and rollback metadata
- last verification result and status

Write state atomically and lock exposure mutations so concurrent `manage.sh` processes cannot allocate the same port or corrupt the lease registry.

After creation, verify both the local listener and an application-aware path when a safe health probe is declared. A successful bind alone is not proof that traffic reaches the service. On verification failure, roll back resources created by the current operation and preserve a redacted failure record.

`expose status` must distinguish at least:

- `active`: listener exists and target verification passes
- `degraded`: listener exists but target verification fails or is inconclusive
- `expired`: TTL elapsed
- `stale`: owned listener no longer exists or its runtime target changed
- `conflicted`: endpoint is now occupied by a non-owned listener

`expose cleanup` removes expired and safely identifiable stale bundle-owned resources after preview. It must not delete conflicted or ambiguously owned resources automatically.

## Documentation And Tests

Generate Simplified Chinese operations documentation containing the actual commands, public-listen warning, TTL and reboot behavior, status meanings, removal procedure, and runtime-specific limitations.

At minimum, test:

- target-port inference and ambiguous-port rejection
- IPv4, bracketed IPv6, invalid endpoint, and port-range parsing
- wildcard-versus-specific-address conflict detection
- idempotent add and remove
- public-exposure confirmation gates
- TTL expiry and cleanup
- stale helper process, container replacement, pod replacement, and no-ready-endpoint behavior
- concurrent allocation locking
- verification failure rollback
- Docker temporary and persistent adapters
- K3s exact-listener and NodePort adapters
- offline dependency availability
- uninstall ownership boundaries
