# 个人 Codex Skills

这个仓库用来保存我自己开发的 Codex skills，以及对应的设计说明。

## Skills 列表

- `ssh-linux-diagnose`：专门用于通过 SSH 或人工转执行命令的方式诊断 Linux 服务器。它会先访谈澄清故障，再执行诊断；所有远程命令都需要 AI 二次审核；涉及状态变更或高危命令文本时，必须先获得人工确认。

## 安装

把 skill 目录复制到个人 Codex skills 目录：

```bash
mkdir -p ~/.agents/skills
cp -R skills/ssh-linux-diagnose ~/.agents/skills/
```

## 目录结构

- `skills/`：可安装的 skill 目录。
- `docs/plans/`：已批准的设计文档和实现计划。
