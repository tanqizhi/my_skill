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
关键假设：...
```

Ask the user to confirm the summary when an incorrect assumption would cause substantial rework, external access, or unsafe behavior.

## Must Ask Before Proceeding

Pause and ask when:

- service ownership between PaaS and SaaS is ambiguous and affects package selection;
- a SaaS service depends on excluded PaaS services and no dependency policy is known;
- image versions conflict with application or platform compatibility requirements;
- a high or critical vulnerability has no clearly compatible fixed version;
- a private registry requires credentials, custom CA trust, or insecure-registry configuration;
- an operation would overwrite configuration, remove containers, delete images, remove volumes, or touch persistent data;
- host changes are required, including firewall, SELinux, sysctl, package installation, systemd, storage, or network configuration;
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
