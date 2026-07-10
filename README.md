# 个人 Codex Skills

这个仓库用来保存我自己开发的 Codex skills，以及对应的设计说明。

## Skills 列表

- `ssh-linux-diagnose`：专门用于通过 SSH 或人工转执行命令的方式诊断 Linux 服务器。它会先访谈澄清故障，再执行诊断；所有远程命令都需要 AI 二次审核；涉及状态变更或高危命令文本时，必须先获得人工确认。
- `network-security-integrated-scanner`：集成外部 Nmap/Nuclei/长亭 Xray 扫描、已有漏扫报告定向验证、Linux SSH 内部检查与可选深度取证，生成技术 Markdown、领导版离线 HTML、结构化 JSON 和证据包。
- `network-secure`：精简的网络安全评估工作流 Skill，支持外部扫描、Linux SSH 内检、既有漏扫报告验证和领导版 HTML 报告。

## 安装

把 skill 目录复制到个人 Codex skills 目录：

```bash
mkdir -p ~/.agents/skills
cp -R skills/ssh-linux-diagnose ~/.agents/skills/
cp -R skills/network-security-integrated-scanner ~/.agents/skills/
cp -R skills/network-secure ~/.agents/skills/
```

## 目录结构

- `skills/`：可安装的 skill 目录。
- `docs/plans/`：已批准的设计文档和实现计划。
