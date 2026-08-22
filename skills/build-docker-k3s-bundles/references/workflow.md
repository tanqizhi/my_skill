# Workflow

Use this reference when planning a new bundle, modifying an existing bundle, or explaining the execution state to the user.

## Main Flow

```mermaid
flowchart TB
    START([开始]) --> TASK{任务类型}

    TASK -->|新建安装包| REQUIREMENT[收集并确认需求]
    TASK -->|改造现有安装包| SCAN[扫描现有包、清单、脚本和生成物]
    SCAN --> FW_SCAN[扫描iptables、nftables、firewalld和持久化操作]
    FW_SCAN --> FW_EXISTING{是否已有bundle专属NAT链}
    FW_EXISTING -->|已确认归属和用途| FW_REUSE[记录并复用原链名和挂载位置]
    FW_EXISTING -->|没有| REQUIREMENT
    FW_EXISTING -->|归属不明或冲突| FW_CONFIRM[列出候选链、规则和影响并请求确认]
    FW_REUSE --> REQUIREMENT
    FW_CONFIRM --> REQUIREMENT

    REQUIREMENT --> ENVIRONMENT[确认系统、架构、网络、权限和测试环境]
    ENVIRONMENT --> DEPLOY_TARGET{部署目标}
    DEPLOY_TARGET -->|Docker| INVENTORY
    DEPLOY_TARGET -->|K3s或两者| K3S_TOPOLOGY[确认server和agent拓扑、名称、IP及登录方式]
    K3S_TOPOLOGY --> INVENTORY[建立完整服务、镜像和依赖清单]

    INVENTORY --> CONTENT_SCOPE{安装包内容范围}
    CONTENT_SCOPE -->|完整| SELECT_FULL[选择全部PaaS和SaaS服务]
    CONTENT_SCOPE -->|仅PaaS| SELECT_PAAS[筛选PaaS服务]
    CONTENT_SCOPE -->|仅SaaS| SELECT_SAAS[筛选SaaS服务]
    CONTENT_SCOPE -->|自定义| SELECT_CUSTOM[交互式选择服务]

    SELECT_FULL --> HAS_SAAS
    SELECT_PAAS --> DEPENDENCY_POLICY
    SELECT_SAAS --> HAS_SAAS
    SELECT_CUSTOM --> HAS_SAAS

    HAS_SAAS{是否包含SaaS组件}
    HAS_SAAS -->|否| DEPENDENCY_POLICY
    HAS_SAAS -->|是| SAAS_DEPENDENCIES[枚举每个SaaS依赖的全部PaaS和外部目标]
    SAAS_DEPENDENCIES --> DEP_INIT{SaaS启动前是否初始化依赖数据或配置}
    DEP_INIT -->|是| INIT_PLAN[定义来源、摘要、目标、顺序、幂等、备份、验证和回滚]
    DEP_INIT -->|否| INIT_SKIP[记录跳过原因和前置条件]
    INIT_PLAN --> CONFIG_AUDIT[核对SaaS启动配置和凭据注入方式]
    INIT_SKIP --> CONFIG_AUDIT
    CONFIG_AUDIT --> CONNECTION_CHECK[定义安装前连接和配置一致性检查]
    CONNECTION_CHECK --> DEPENDENCY_POLICY

    DEPENDENCY_POLICY{未选中的依赖如何处理}
    DEPENDENCY_POLICY -->|一并包含| INCLUDE_DEPENDENCIES[加入必要依赖]
    DEPENDENCY_POLICY -->|使用外部服务| EXTERNAL_DEPENDENCIES[记录外部地址和安装前检查]
    DEPENDENCY_POLICY -->|分层安装包| LAYERED_DEPENDENCIES[生成包依赖和版本约束]
    INCLUDE_DEPENDENCIES --> PACKAGE_MODE
    EXTERNAL_DEPENDENCIES --> PACKAGE_MODE
    LAYERED_DEPENDENCIES --> PACKAGE_MODE

    PACKAGE_MODE{安装包类型}
    PACKAGE_MODE -->|完整可安装包| INSTALLABLE[准备镜像、配置、运行时和脚本]
    PACKAGE_MODE -->|仅镜像包| IMAGES_ONLY[只准备镜像、摘要、清单和导入脚本]
    PACKAGE_MODE -->|升级包| UPGRADE[准备差异、迁移、升级和回滚内容]

    INSTALLABLE --> IMAGE_SOURCE
    IMAGES_ONLY --> IMAGE_SOURCE
    UPGRADE --> IMAGE_SOURCE

    IMAGE_SOURCE{镜像来源}
    IMAGE_SOURCE -->|公共仓库| VERSION[解析兼容版本和可信摘要]
    IMAGE_SOURCE -->|私有仓库| REGISTRY[确认地址、认证方式和证书]
    IMAGE_SOURCE -->|用户提供| PROVIDED[核验镜像文件、架构和摘要]
    REGISTRY --> VERSION
    PROVIDED --> CLASSIFY

    VERSION --> SECURITY[检查漏洞、许可证、来源和兼容性]
    SECURITY --> SECURITY_RESULT{符合安全策略}
    SECURITY_RESULT -->|是| ACQUIRE[下载或复制并按可信摘要核验]
    SECURITY_RESULT -->|存在兼容安全版本| VERSION
    SECURITY_RESULT -->|需要风险接受| EXCEPTION[说明风险并请求明确确认]
    SECURITY_RESULT -->|不可接受| FAIL([终止并输出原因])
    EXCEPTION --> ACQUIRE

    ACQUIRE --> CLASSIFY[标记PaaS或SaaS、服务归属和依赖]
    CLASSIFY --> MANIFEST[生成bundle清单、初始化计划、部署配置和环境变量模板]
    MANIFEST --> ARTIFACTS{是否仅镜像包}
    ARTIFACTS -->|是| VALIDATE
    ARTIFACTS -->|否| RUNTIME[准备Docker、Compose或K3s运行时文件]
    RUNTIME --> MODULES[生成可续装安装、重装、管理、升级和回滚模块]
    MODULES --> NETWORK[生成Docker端口、NodePort和bundle专属NAT管理模块]
    NETWORK --> REPORTER[生成安装后部署与运维报告模块]
    REPORTER --> VALIDATE[执行静态检查和自动化测试]

    VALIDATE --> VALID_RESULT{检查是否通过}
    VALID_RESULT -->|否| FIX[修复问题并记录变化]
    FIX --> VALIDATE
    VALID_RESULT -->|是| PACKAGE[生成安装包、校验清单、SBOM或来源记录和说明文档]

    PACKAGE --> TEST_HOST{是否提供Linux测试环境}
    TEST_HOST -->|否| STATIC_ONLY[标记仅完成静态验证]
    TEST_HOST -->|是| CONFIRM_REMOTE[确认上传和执行测试]
    CONFIRM_REMOTE --> INSTALL_TEST[执行安装、失败续装、重装、升级、端口、NAT和回滚测试]
    INSTALL_TEST --> TEST_RESULT{测试是否通过}
    TEST_RESULT -->|否| FIX
    TEST_RESULT -->|是| SUCCESS([交付完成])
    STATIC_ONLY --> SUCCESS
```

## Installation, Resume, and Reinstall Flow

```mermaid
flowchart TB
    ENTRY([执行install.sh]) --> MODE{执行模式}
    MODE -->|首次安装| NEW_STATE[创建原子状态文件和清单指纹]
    MODE -->|resume| LOAD_STATE[读取阶段状态、输入指纹和失败原因]
    MODE -->|restart-from| RESET_FROM[确认起始阶段并使下游检查点失效]
    MODE -->|reinstall| REINSTALL_TARGET[选择服务或阶段]

    LOAD_STATE --> INPUT_CHANGED{清单或配置输入是否变化}
    INPUT_CHANGED -->|否| FIND_STAGE[定位首个失败或未完成阶段]
    INPUT_CHANGED -->|是| INVALIDATE[仅使受影响阶段及其下游失效]
    INVALIDATE --> FIND_STAGE

    REINSTALL_TARGET --> CLEAN_MODE{是否清理持久化数据}
    CLEAN_MODE -->|否| PRESERVE[保留数据和用户配置]
    CLEAN_MODE -->|是| BACKUP_CONFIRM[备份并请求破坏性操作确认]
    PRESERVE --> RESET_TARGET[清除目标和受影响下游检查点]
    BACKUP_CONFIRM --> RESET_TARGET

    NEW_STATE --> NEXT
    FIND_STAGE --> NEXT
    RESET_FROM --> NEXT
    RESET_TARGET --> NEXT

    NEXT[执行下一阶段] --> STAGE_CHECK[预检查]
    STAGE_CHECK --> STAGE_APPLY[执行]
    STAGE_APPLY --> STAGE_VERIFY[验证实际结果]
    STAGE_VERIFY --> STAGE_RESULT{阶段是否成功}

    STAGE_RESULT -->|成功| CHECKPOINT[原子记录输入摘要、输出和验证结果]
    CHECKPOINT --> MORE{还有阶段吗}
    MORE -->|有| NEXT
    MORE -->|没有| SUCCESS_REPORT[生成成功部署与运维报告]

    STAGE_RESULT -->|失败| FAILURE_STATE[记录失败阶段、节点、原因和续装命令]
    FAILURE_STATE --> FAILURE_REPORT[生成失败或部分成功报告]
    FAILURE_REPORT --> EXIT_FAIL([保留原始退出码])
    SUCCESS_REPORT --> EXIT_OK([安装完成])
```

Stage order for a bundle that contains SaaS is: preflight, runtime, image import, PaaS deployment or dependency validation, declared dependency initialization, SaaS configuration validation, SaaS deployment, approved exposure and NAT changes, health validation, and reporting. Skip only stages that are not applicable and record the reason.

## Management Flow

```mermaid
flowchart TB
    START[管理入口] --> LOAD[读取bundle清单、检查点和实际状态]
    LOAD --> ACTION{选择操作}

    ACTION -->|启动、停止或重启| GROUP[选择PaaS、SaaS、全部或单个服务]
    GROUP --> EXECUTE[执行操作并检查健康状态]
    ACTION -->|状态或版本| STATUS[显示运行、健康、节点、依赖、标签和摘要]
    ACTION -->|导入或切换镜像| IMAGE_MANAGE[执行映射、兼容性、备份、切换、验证和回滚]

    ACTION -->|对外端口管理| EXPOSURE_TARGET{Docker还是K3s}
    EXPOSURE_TARGET -->|Docker| DOCKER_PORTS[读取发布地址、宿主端口、容器端口和协议]
    EXPOSURE_TARGET -->|K3s| NODE_PORTS[读取Service、NodePort和集群实际端口范围]
    DOCKER_PORTS --> EXPOSURE_CRUD{增删改查}
    NODE_PORTS --> EXPOSURE_CRUD
    EXPOSURE_CRUD --> EXPOSURE_PRECHECK[检查端口冲突、范围、配置归属和影响服务]
    EXPOSURE_PRECHECK --> EXPOSURE_PREVIEW[显示差异并请求确认]
    EXPOSURE_PREVIEW --> EXPOSURE_APPLY[备份后重建受影响容器或Patch Service]
    EXPOSURE_APPLY --> EXPOSURE_VERIFY{连通性和健康检查}
    EXPOSURE_VERIFY -->|成功| COMPLETE[记录状态并更新报告]
    EXPOSURE_VERIFY -->|失败| EXPOSURE_ROLLBACK[恢复原端口配置]

    ACTION -->|NAT管理| FW_PREFLIGHT[检测iptables、iptables-nft、nftables、firewalld和权限]
    FW_PREFLIGHT --> FW_DISCOVER[检测同名链、PREROUTING跳转、规则归属和持久化]
    FW_DISCOVER --> FW_COMPATIBLE{现有链是否兼容}
    FW_COMPATIBLE -->|是| FW_REUSE[复用同名链并仅补齐缺失项]
    FW_COMPATIBLE -->|没有| FW_CREATE[创建bundle专属链并挂载一次]
    FW_COMPATIBLE -->|不明确或冲突| FW_STOP[停止并请求确认]
    FW_REUSE --> FW_CRUD
    FW_CREATE --> FW_CRUD
    FW_CRUD{列出、新增、修改、删除、调整位置或同步}
    FW_CRUD --> FW_PREVIEW[显示规则ID、位置、命令和差异]
    FW_PREVIEW --> FW_CONFIRM[确认提权和应用]
    FW_CONFIRM --> FW_SNAPSHOT[保存目标节点规则快照]
    FW_SNAPSHOT --> FW_CLUSTER{是否集群}
    FW_CLUSTER -->|否| FW_APPLY[本节点原子应用并验证]
    FW_CLUSTER -->|是| FW_ALL_NODES[同步到每个server和agent节点]
    FW_ALL_NODES --> NODE_RESULT{当前节点是否成功}
    NODE_RESULT -->|成功且还有节点| FW_ALL_NODES
    NODE_RESULT -->|全部成功| FW_VERIFY[比较所有节点规则摘要]
    NODE_RESULT -->|失败| NODE_PROMPT[显示节点名、IP、原因和本机手工恢复命令]
    NODE_PROMPT --> DECISION{继续还是回滚}
    DECISION -->|继续| FW_CONTINUE[记录失败节点并继续其余节点]
    FW_CONTINUE --> FW_ALL_NODES
    DECISION -->|回滚| FW_ROLLBACK[恢复本次已修改节点的规则快照]
    FW_APPLY --> FW_VERIFY
    FW_VERIFY --> COMPLETE
```

In non-interactive mode, a node failure must stop unless the caller explicitly supplied an on-failure policy of `continue` or `rollback`. Continuing never turns the failed node into a success: retain its node name, IP, error, and exact local command in state and in the deployment report.

## Modification Flow

For an existing bundle:

1. Inventory the current files, service definitions, scripts, image archives, checksums, generated outputs, installation state, and user-managed overrides.
2. Inspect installation, management, uninstall, persistence, systemd, iptables, iptables-restore, nftables, and firewalld code before proposing network changes.
3. Reconstruct or update the bundle manifest before editing duplicated deployment files.
4. If an existing user-defined NAT chain and PREROUTING jump are verified as bundle-owned and semantically compatible, preserve their exact chain name and placement. Do not create a parallel chain.
5. Calculate the requested delta: add, remove, upgrade, reclassify, change deployment target, change bootstrap data, expose ports, or manage NAT rules.
6. Preserve user-managed configuration and persistent data unless the user explicitly approves migration or replacement.
7. Regenerate only affected adapters and artifacts.
8. Test both the changed path and compatibility with an existing installation, including repeated execution and resume after a controlled failure.
