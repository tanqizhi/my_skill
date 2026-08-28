# Simplified Chinese Deliverables

Read this reference when generating an installable or upgrade bundle, its terminal report, operator documentation, or uninstall behavior.

## Language and File Requirements

Generate these UTF-8 Markdown files:

- `reports/deployment-and-operations.md`: Simplified Chinese deployment and current-state report;
- `docs/installation-guide.zh-CN.md`: Simplified Chinese installation and uninstall manual;
- `docs/operations-guide.zh-CN.md`: Simplified Chinese operations and management manual.

Use Simplified Chinese for titles, headings, instructions, warnings, status explanations, troubleshooting, and table labels. Keep commands, flags, file paths, resource names, image names, protocol fields, and untranslatable product terminology in their exact technical form, then explain them in Chinese. Do not translate commands in a way that makes them unusable.

Generate documentation from the actual bundle manifest, generated scripts, paths, services, nodes, ports, and enabled features. Remove sections that are not applicable. Never deliver a generic manual containing unresolved placeholders or claims about tests that were not run.

## Chinese Deployment Report

The report retains the required path `reports/deployment-and-operations.md` and is refreshed after installation, reinstall, upgrade, or uninstall completes, partially completes, or fails.

Use Chinese result labels such as `成功`, `部分成功`, `失败`, `已跳过`, and `未检查`, while retaining stable machine-readable codes when the generated tooling needs them.

Include:

- 操作类型、开始和结束时间、总体结果及原始退出码；
- 目标主机或各集群节点的名称、IP、角色和执行结果；
- 已部署、升级、重装、卸载、保留或失败的服务和资源；
- 镜像标签、摘要、运行状态、健康检查、对外地址和端口；
- SaaS 前置依赖初始化及启动配置验证结果；
- 安装或卸载检查点、断点续执行情况和准确恢复命令；
- NAT 表、PREROUTING 挂载、自定义链、规则及各节点同步结果；
- 配置、数据、日志、备份、状态文件、安装手册和运维手册路径；
- 未执行检查、剩余人工步骤、风险、回滚和恢复方式。

Do not copy secrets or credential-bearing command lines into the report.

## Chinese Installation and Uninstall Manual

`docs/installation-guide.zh-CN.md` must cover the actual bundle:

1. 安装包用途、内容范围、支持系统、架构和部署目标；
2. 安装前资源、端口、网络、权限、依赖和凭据注入准备；
3. 配置文件、节点清单、镜像和校验方式；
4. 首次安装、`--dry-run`、非交互安装和安装结果验证；
5. `--status`、`--resume`、`--restart-from` 和 `--reinstall`；
6. `install.sh --uninstall` 的默认保留行为和执行步骤；
7. 数据清理、镜像删除或专属运行时移除的独立选项、影响、备份和确认要求；
8. 卸载中断后的状态查看、续执行、人工恢复和结果验证；
9. 常见安装或卸载错误、日志位置、报告位置和排查方法。

Every command must match the generated script's real CLI. Do not document an option that the bundle does not implement.

## Chinese Operations and Management Manual

`docs/operations-guide.zh-CN.md` must cover the enabled management capabilities:

- 服务启动、停止、重启、状态、健康检查、版本和日志；
- PaaS、SaaS、全部服务和单个服务的选择方式；
- `manage.sh` 的模块化命令结构，以及 Compose/K3s 配置修改后的快速校验、预览、重载、验证和回滚；
- 镜像导入、切换、版本核对和失败回滚；
- Docker 发布端口和 K3s NodePort 的查询、增删改、冲突检查和恢复；
- bundle 专属 NAT 链的查询、增删改、规则位置、同步、漂移检查、修复和持久化；
- 集群节点失败时的继续或回滚选择，以及节点名、IP 和本机恢复命令；
- 配置、数据、日志、状态、备份和报告的位置；
- 备份、升级、回滚、故障恢复和卸载入口；
- 权限要求、危险操作提示和不会被工具自动处理的外部依赖。

Prefer copy-ready examples derived from the generated bundle. Clearly label destructive or privileged operations in Chinese and keep secret values out of examples.

## Uninstall Contract

`install.sh --uninstall` is required for installable bundles. It is an operation state machine, not an unconditional cleanup script.

Before uninstall:

1. load the manifest and installation or uninstall checkpoints;
2. discover actual resources on every target node;
3. classify each resource as bundle-owned, shared, external, user-managed, or ambiguous;
4. show a Chinese preview of removed, retained, skipped, and blocked resources;
5. obtain confirmation immediately before mutation.

Default uninstall removes only verified bundle-owned runtime resources and preserves persistent data, user configuration, images, shared runtimes, backups, reports, manuals, and resumable state.

Use separate explicit switches for destructive scopes. Recommended names are `--purge-data`, `--remove-images`, and `--remove-runtime`, but the generated CLI may use repository conventions if the Chinese manual documents the exact choices. Never infer a destructive scope from `--uninstall` alone.

Uninstall in reverse dependency order. Remove bundle-owned exposure and NAT entries without changing foreign rules. For a cluster, execute and verify every declared node. Apply the existing node-failure continue-or-rollback interaction and show an exact local recovery command.

Record an atomic checkpoint after each verified stage. Support `install.sh --uninstall --resume` or an equivalent documented form. Keep enough state and reports to audit or continue a partial uninstall.
