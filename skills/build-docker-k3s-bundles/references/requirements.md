# Requirements and Confirmations

## Initial Questions

Ask only unanswered questions that materially affect the output. Group related questions to reduce repeated interruptions.

1. Is this a new bundle or a modification of an existing bundle?
2. What is the content scope: `full`, `paas`, `saas`, or `custom`?
3. What is the package mode: `installable`, `images-only`, or `upgrade`?
4. What is the deployment target: Docker, K3s, or both?
5. Which Linux distributions and CPU architectures must be supported?
6. Is the environment online, proxy-only, partially offline, or fully offline?
7. Which services and image versions are required, and which images are public, private, or supplied as archives?
8. For SaaS-only or custom bundles, should missing dependencies be included, external, or supplied by a layered PaaS package?
9. For K3s, what are the server/agent roles, node addresses, SSH method, registry arrangement, and storage/network requirements?
10. Is a Linux test environment available, and may the skill upload and execute the generated package there?
11. If SaaS is included, which PaaS or external dependencies of any type require data, configuration, metadata, policies, identities, or other initialization before SaaS starts? Database content and Nacos configuration are examples, not an exhaustive type list.
12. For each SaaS service, which dependency targets of any type must its startup configuration reference, and which provider-specific selectors and validation rules apply?
13. Which Docker published ports or K3s NodePorts must be exposed, and should the bundle manage external DNAT rules?
14. If NAT management is required, which nodes, interfaces, destination addresses, protocols, ports, rule ordering, backend, and reboot-persistence behavior are required?
15. For modifications, do existing scripts already create a user-defined chain or attach it to `nat/PREROUTING`, and is that chain known to belong to this bundle?
16. For uninstall, which bundle-owned workloads, exposure rules, NAT rules, generated configuration, and images may be removed, and which persistent data, user configuration, backups, reports, and runtimes must be retained?

Do not ask the user to paste reusable passwords, private keys, registry tokens, or K3s tokens into chat. Ask how credentials will be injected at execution time.

## Requirement Summary

Before generating or materially changing artifacts, summarize the resolved dimensions:

```text
任务类型：新建 / 改造
内容范围：full / paas / saas / custom
安装包类型：installable / images-only / upgrade
部署目标：docker / k3s / both
目标系统：发行版和版本
CPU架构：amd64 / arm64 / other
网络模式：online / proxy / partial-offline / offline
依赖策略：include / external / layered
镜像来源：public / private / provided
测试级别：static-only / local / remote-single-node / remote-multi-node
SaaS前置依赖初始化：required / skipped / not-applicable
SaaS依赖配置：全部依赖目标、类型、选择参数和验证方式
安装恢复：checkpoint / resume / reinstall策略
端口暴露：Docker发布端口 / K3s NodePort
NAT管理：disabled / single-node / all-cluster-nodes
NAT链：复用现有链 / 新建专属链 / 待确认
卸载策略：默认保留数据 / 可选清理数据、镜像或专属运行时
中文交付：部署报告 / 安装手册 / 运维管理手册
关键假设：...
```

Ask the user to confirm the summary when an incorrect assumption would cause substantial rework, external access, or unsafe behavior.

## Must Ask Before Proceeding

Pause and ask when:

- service ownership between PaaS and SaaS is ambiguous and affects package selection;
- a SaaS service depends on excluded PaaS services and no dependency policy is known;
- SaaS is included but the need, source, order, idempotency, backup, validation, or rollback behavior of required dependency-initialization tasks is unknown;
- a SaaS startup configuration does not identify or cannot validate any required dependency target or its provider-specific selectors;
- image versions conflict with application or platform compatibility requirements;
- a high or critical vulnerability has no clearly compatible fixed version;
- a private registry requires credentials, custom CA trust, or insecure-registry configuration;
- an operation would overwrite configuration, remove containers, delete images, remove volumes, or touch persistent data;
- uninstall would delete persistent data, user configuration, images, backups, reports, the bundle state needed for resume, a shared runtime, or any resource whose ownership is ambiguous;
- host changes are required, including firewall, SELinux, sysctl, package installation, systemd, storage, or network configuration;
- an existing same-name NAT chain or PREROUTING jump has ambiguous ownership, incompatible rules, or multiple possible chain names;
- a NAT rule is about to be created, changed, removed, repositioned, persisted, or synchronized to a node;
- a cluster NAT rollout fails on any node; show the node name, IP address, failure reason, and exact local recovery command, then ask whether to continue or roll back;
- remote login, file upload, installation, restart, or cluster joining is about to occur;
- password-based SSH, `sshpass`, sudo, or another elevated mechanism is proposed;
- installation, upgrade, health, or rollback testing fails and the next step changes the agreed design;
- the user must accept a known security, compatibility, license, or operational risk.

## Safe Defaults

Unless repository conventions say otherwise:

- use a declarative bundle manifest as the source of truth;
- prefer a layered dependency policy for reusable PaaS plus SaaS packages;
- prefer SSH keys over password automation;
- prefer immutable image digests while retaining tags for display;
- use non-secret environment templates and runtime secret injection;
- generate `--dry-run` and non-interactive modes when appropriate;
- preserve existing user configuration during modifications;
- preserve persistent data and user configuration during reinstall; require explicit confirmation for clean or destructive reinstall;
- make uninstall resumable and remove only verified bundle-owned runtime resources by default;
- preserve persistent data, user configuration, images, shared runtimes, backups, reports, manuals, and uninstall state unless separately requested and confirmed;
- generate the deployment report, installation guide, and operations guide in Simplified Chinese;
- write atomic per-stage installation checkpoints and resume from the first invalid, failed, or incomplete stage;
- leave external firewall management disabled unless requested;
- reuse an existing NAT chain only after verifying that it belongs to the bundle and serves the same purpose;
- when cluster NAT management is enabled, target every declared server and agent node;
- in non-interactive mode, stop on a node failure unless an explicit `continue` or `rollback` policy was supplied;
- stop after static validation when no authorized test host exists.

List applied defaults in the final report.

## Stopping Rules

When blocked:

1. Stop at the affected step without performing the risky action.
2. Preserve completed non-destructive artifacts.
3. State the current stage and exact blocking condition.
4. Offer practical options and explain their effects.
5. Continue only after the user resolves the blocking decision.

Never convert silence into permission for destructive actions, remote changes, credential use, or risk acceptance.
