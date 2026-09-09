# 可移植管理基座

## 边界与交付物

这是**管理工具，不是安装器**。安装、迁移目录、创建安装记录、重装、卸载和整包升级属于 `install.sh`。管理器只读取规范目录和显式注册的配置，执行已实现的管理操作；缺文件或身份不匹配时停止，不猜测、不自动初始化安装环境。

资源均位于本 skill 的 `assets/management-base/`：

| 路径 | 用途 |
| --- | --- |
| `source/managebase/`、`source/manage.py` | 可读 Python 业务源码、开发入口 |
| `source/vendor/` | 固定版本 ruamel.yaml 0.18.6 纯 Python 源码及许可 |
| `source/tools/package.py` | 可重现构建应用 zipapp |
| `source/tools/portable.py` | 运行时裁剪及可移植发行包构建 |
| `source/tools/test_management_suite.py`、`source/tests/` | 管理能力回归测试 |
| `source/tools/test_portable.py` | 空文件系统、CLI、真实 PTY 可移植性测试 |
| `runtime/python-runtime-linux-x86_64-static.tar.gz` | 离线重打包输入，含静态解释器、标准库、终端数据库、许可与来源 |
| `releases/managebase-linux-x86_64-static.tar.gz` | 可直接放进安装包的管理器发行包 |
| `runtime/*.sha256`、`releases/*.sha256` | 归档校验值 |
| `validation/` | 本次构建的验证结果，按实际 artifact SHA256 关联 |

发行包解开后为 `manage.sh`、`manage.pyz`、`runtime/python/`、`management/release.json`、`management/checksums.txt`。安装器把这些放在**安装根目录**，不可多套一层管理器目录；不要只复制 `manage.pyz`。不带业务配置、数据、镜像、凭据、安装记录或旧安装器。

## 平台与自依赖程度

- 当前产物是 Linux **x86_64/amd64** 基线架构，CPython 3.12.14，python-build-standalone 20260901 的 `lto+static-full` 构建，musl 1.2.5。
- 自带解释器、Python 标准库、静态 curses/ncurses、终端数据库和 YAML 依赖。不需要系统 Python、pip、动态 glibc/musl、ncurses 包或系统 terminfo；启动不下载任何依赖。
- `manage.sh` 只要求目标机有 POSIX `/bin/sh`。无 shell 的特殊环境可直接使用 `runtime/python/bin/python3.12 -I -B -X utf8 /绝对安装根目录/manage.pyz ...`，但交互模式还需设置 `LC_ALL=C.UTF-8`、`TERMINFO`、`TERMINFO_DIRS` 指向随包目录，保持有效的 `TERM` 和 UTF-8 终端。
- 保持整个目录树一起搬运。不要通过符号链接启动 `manage.sh`；从真实路径或 PATH 启动。已有实例搬家必须由安装器更新身份和挂载配置，不能只移动目录后假定业务可用。
- 静态解释器不支持加载新增的 Python 原生 `.so` 扩展；优先纯 Python 依赖。不要误用上游 musl `install_only` 包，它不是这里验证的全静态运行时。
- ARM64、其他 CPU、非 Linux、最低内核版本及任意发行版组合未得到本产物的兼容承诺。跨发行版缺动态库问题已用空文件系统测试覆盖；仍需在实际目标平台做验收。
- 操作系统内核、文件权限、终端字体和下列被管理系统接口不会被“自依赖”消除。

## 外部接口

| 接口 | 约束 |
| --- | --- |
| Docker CLI | 安装器验证绝对路径并写入 `compose.docker_binary`；管理器不下载安装 |
| Docker Compose v2 | CLI 必须支持本管理器实际调用的 `docker compose` 参数；制作包时测试配置解析及变更流程 |
| Docker Engine | 只用本机 `unix:///var/run/docker.sock`；需要相应读写权限，不支持远程 context 或 rootless socket |
| Docker CLI 配置 | 可选固定 `config/services/installer/docker-cli/config.json`，用来显式定位离线 Compose 插件等；不能依赖用户 HOME 隐式配置 |
| 防火墙 | 使用宿主机匹配 Docker 后端的 iptables/ip6tables 与查询接口；需要网络管理权限及已存在的 `filter/DOCKER-USER` 链；不得强行换成另一套后端 |
| 文件系统 | 配置、备份和锁需要合适权限、空间以及 Linux 文件锁/原子写语义；普通状态查询不应触发业务变更 |

防火墙添加是**主机级、DNAT 后匹配、运行时生效**：IP/tcp/udp/icmp、IPv4/IPv6、CIDR、可选端口/范围、ACCEPT/REJECT，行号从 1 开始，`-1` 是实际末尾。不会创建/清空链，不做重启持久化，不等同于 bundle-owned NAT/exposure 管理。备份、计划、恢复指引放在 `backups/firewall-add-<id>/`；失败时只尝试删除本次唯一标记规则。共享锁另用 `/run/lock/managebase-docker-firewall.lock`。

## 安装器必须提供的路径与记录

默认根目录 `/opt/bundles/<bundle-name>`，允许首次安装显式指定另一绝对目录。根目录不能是 `/`。ID 使用小写字母开头的小写字母、数字、连字符，最长 63 字符。读取配置不允许符号链接跳转。详细所有权与存储例外见 `installation-layout.md`。

固定读取：

1. `state/installation.json`：JSON 对象，禁止重复字段、不能作为 Shell 执行。
2. `bundle.yaml`：已安装清单，无真实凭据。
3. `deploy/docker/compose.yaml`：基础 Compose。
4. `config/compose.override.yaml`：必须存在，后加载；无覆盖也写有效空配置。
5. `config/compose.env`：必须存在，显式加载；无变量可为空。

安装器原子写入的最小记录示例（其中 Docker 路径必须换成实际验证过的路径）：

```json
{
  "layout_version": 1,
  "bundle_name": "example",
  "bundle_version": "1.0.0",
  "instance_id": "example-one",
  "install_root": "/opt/bundles/example",
  "deploy_targets": ["docker"],
  "storage": [],
  "compose": {
    "project_name": "example-one",
    "docker_binary": "/usr/bin/docker",
    "files": ["deploy/docker/compose.yaml", "config/compose.override.yaml"],
    "env_files": ["config/compose.env"],
    "profiles": [],
    "docker_config": "config/services/installer/docker-cli"
  }
}
```

`docker_config` 可省略；填写时只能是示例固定目录且必须包含 `config.json`。`files`、`env_files` 顺序和名称必须完全一致；`profiles` 必须是去重列表。`install_root` 必须等于实际规范化绝对路径。`storage` 按清单记录真实所有权，不能用空列表掩盖外置存储。

还应由安装器创建 `state/locks/`，实例变更使用 `state/locks/management.lock`。持久化目录为 `data/<service>/`，服务配置为 `config/services/<service>/`，凭据为 `secrets/<service>/`，文件日志为 `logs/services/<service>/`；均由安装器按实际服务配置权限。管理器按操作在 `backups/<operation-id>/` 建立受保护备份，导入时间记入 `state/image-import/<digest>.json`。

管理器读取实时 Docker/Compose 信息，不只信任安装记录。安装器需让容器保留正确 Compose 项目/服务标签，挂载指向已登记的规范路径。`layout` 只验证入口所需固定文件与身份，不代表完整安装验收或服务健康。

## 命令与能力

无参数进入全屏菜单；任意参数保持非交互，不回退菜单。CLI 使用 `--help` 查看完整语法，`--json` 输出结构化结果，`--root` 指定已安装实例；默认根目录来自程序实际位置而非工作目录。变更必须给完整选择参数和 `--yes`，预览用 `--dry-run`。预览可能查询当前系统，但不应实施变更。

| 命令 | 当前实现与限制 |
| --- | --- |
| `doctor`、`layout` | 工具环境、固定路径和实例身份检查 |
| `status`、`image-versions`、`locations` | 状态、镜像和容器相关位置表；未知时间不得伪造 |
| `exposed-ports`、`docker-firewall` | 端口表、DOCKER-USER 规则和计数查询 |
| `start`、`stop`、`restart` | 指定容器或本实例全部容器，显式确认 |
| `image-import` | Docker-save tar/gzip/bzip2/xz，编辑名称/tag，拒绝标签冲突；不支持纯 OCI、zstd、docker-export |
| `image-switch` | 所选服务使用已有本地镜像，不 pull/build，不启动依赖；校验漂移、备份、健康验证及失败恢复尝试 |
| `service-add` | 从输入 Compose 提取指定服务写入固定 override，创建但不启动；只用规范 bind 路径，不隐式创建命名/匿名卷 |
| `config-check` | 调用实际 Compose 配置校验 |
| `backup-compose`、`backup-data` | 单服务或全部，tar.gz，拒绝覆盖；在线文件备份不是数据库事务一致备份 |
| `firewall-add` | 上述现存 DOCKER-USER 链的受控规则添加 |

成功通常退出 0；参数/授权错误为非零，`--help`/`--version` 为 0。不要把错误输出解析成成功数据；结构化业务结果字段由 `source/managebase/model.py` 与 `cli.py` 定义。通用 reload、exposure CRUD、K3s、自动通用 restore、安装/卸载/整包升级**未实现**。不得从旧设计文档推断它们已经可用，或为填菜单而生成另一套管理脚本。

## 离线重打包与项目定制

优先直接复用发行包，按 `.sha256` 和内部 `management/checksums.txt` 校验。先核对目标、目录契约、所需命令和验证记录；项目名称/目录差异通过安装配置解决。

确有能力差异时，把 `source/` **复制到独立项目构建目录**，修改 Python 模块并保留测试。不要在制作某个项目安装包时改写 skill 标准源或标准产物。使用 skill 中运行时归档离线构建，无需编译器、pip 或网络；构建侧 Python 需要 3.11+，也可使用随发行包的 3.12.14。

在复制出的源码根目录运行（路径替换为本机真实绝对路径）：

```sh
python3 tools/package.py
python3 tools/test_management_suite.py
python3 tools/portable.py build \
  --runtime /path/to/python-runtime-linux-x86_64-static.tar.gz \
  --runtime-sha256 c2c5cb13c56d4a2f75a2f88f3b041a9c1bde7c1107b383c41046a5016d74eea6 \
  --release-name my-project-manager \
  --output /path/to/custom-manager.tar.gz
```

发行包内 `management/release.json` 记录每份源码哈希、应用哈希、运行时输入哈希和平台；归档有独立 SHA256。定制包还需记录项目标识和补丁说明，不自动晋升为公共版。相同源码和运行时输入、相同构建工具链应得到相同归档；不要把文件时间/绝对构建路径写入产物。

变更解释器或架构时不是仅改文件名/平台字符串：需要取得并校验相应静态运行时，修改构建器的固定平台/版本/来源约束，重新做 ELF、模块、终端和业务测试。原生运行时完整重建还需要上游源码及工具链；运行时内 `provenance/` 保存源代码获取清单、版本哈希、构建说明，`licenses/` 保留许可，不能声称只有业务源码就能离线重新编译全部原生依赖。

回归测试可用 `MANAGEBASE_TEST_DOCKER` 指定本地 Docker CLI 绝对路径，`MANAGEBASE_TEST_COMPOSE_DIR` 指定含 `docker-compose` 插件的目录；这些测试只调用配置解析，不启动业务。没有它们时对应集成测试会跳过，必须如实报告，不应把项目镜像或旧安装包复制进 skill 来满足测试。

## 验收

读取 `assets/management-base/validation/` 中与交付归档哈希一致的结果。至少验证：归档/文件哈希、静态 ELF、异目录启动、无系统 Python/动态库/terminfo 环境、CLI 参数错误、无 TTY 拒绝、中文输入、方向键/ESC、终端恢复、固定目录和身份拒绝测试、管理回归、从 skill 源码副本重建。

`test_portable.py` 在无网络的 bubblewrap 空根目录中使用测试专用静态 BusyBox 提供 `/bin/sh`；BusyBox/bubblewrap 不属于管理器运行依赖或发行包。运行例：

```sh
python3 tools/test_portable.py \
  --artifact /path/to/custom-manager.tar.gz \
  --busybox /path/to/test-only-static-busybox \
  --report /path/to/portable-validation.json
```

实际项目仍需经授权在完整部署上测试 Docker/Compose/防火墙接口及其回滚。不能把旧系统 Python 版本的远程测试当成当前静态发行包的远程验收，也不能把 mock 测试当成真实 Docker 变更验证。缺少测试设施时明确列出未测项。
