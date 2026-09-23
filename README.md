# 个人 Codex Skills

这个仓库用来保存我自己开发的 Codex skills，以及对应的设计说明。

## Skills 列表

- `ssh-linux-diagnose`：专门用于通过 SSH 或人工转执行命令的方式诊断 Linux 服务器。它会先访谈澄清故障，再执行诊断；所有远程命令都需要 AI 二次审核；涉及状态变更或高危命令文本时，必须先获得人工确认。
- `network-security-integrated-scanner`：集成外部 Nmap/Nuclei/长亭 Xray 扫描、已有漏扫报告定向验证、Linux SSH 内部检查与可选深度取证，生成技术 Markdown、领导版离线 HTML、结构化 JSON 和证据包。
- `network-secure`：精简的网络安全评估工作流 Skill，支持外部扫描、Linux SSH 内检、既有漏扫报告验证和领导版 HTML 报告。
- `write-report`：将故障、测试、对比等技术材料整理为面向非技术领导的可编辑 Word 报告，强制把核心结论、关键指标、决定性证据和适用边界放进前两页，并附带统一 Word 母版。
- `build-docker-k3s-bundles`：创建或改造 Docker、Docker Compose、K3s 容器安装包，支持全量、仅 PaaS、仅 SaaS、自定义、纯镜像和升级包，并包含依赖处理、安全确认、校验和测试流程。
- `internet-dedicated-line-fault-handling-manual`：上网专线故障接维手动版，适用于4A内网隔离、人工搬运命令和回显的场景；逐轮明确设备类型、目标设备、视图和具体命令，并按内部组织职责给出派单、加派及挂单建议。
- `securecrt-rest-api`：把 SecureCRT 里已连接的会话变成程序可读写的本地 HTTP 接口（只监听 127.0.0.1:19191，无鉴权）；可列 tab、读可见屏与滚动回显、发送命令文本、清屏、停服务。附端点契约与一个不需要 SecureCRT 就能跑的回归脚本，用于先验证端点行为再上真实环境。
- `securecrt-clouddesk`：SecureCRT REST 通道与 clouddesk-diag 云电脑通道的协同用法；先判定 SecureCRT 装在本机还是装在云电脑里（4A 拉起），再给出对应的联合工作流，含云电脑侧桥接脚本 scrt_api.ps1 与通道失败模式对照表。
- `securecrt-clouddesk-dedicated-line`：上网专线故障接维的通道增强版；诊断规则、4A 命令白名单、派单与挂单纪律全部沿用人工版，只把"手工搬运命令"换成经 SecureCRT REST 执行与读回显，并新增通道纪律（发命令前认设备、只读/直发两种模式、一条一发一读、回显落盘留痕、通道不可用时回退人工流程）与每轮输出模板。

## 安装

把 skill 目录复制到个人 Codex skills 目录：

```bash
mkdir -p ~/.agents/skills
cp -R skills/ssh-linux-diagnose ~/.agents/skills/
cp -R skills/network-security-integrated-scanner ~/.agents/skills/
cp -R skills/network-secure ~/.agents/skills/
cp -R skills/write-report ~/.agents/skills/
cp -R skills/build-docker-k3s-bundles ~/.agents/skills/
cp -R skills/internet-dedicated-line-fault-handling-manual ~/.agents/skills/
cp -R skills/securecrt-rest-api ~/.agents/skills/
cp -R skills/securecrt-clouddesk ~/.agents/skills/
cp -R skills/securecrt-clouddesk-dedicated-line ~/.agents/skills/
```

## 目录结构

- `skills/`：可安装的 skill 目录。
- `docs/plans/`：已批准的设计文档和实现计划。
