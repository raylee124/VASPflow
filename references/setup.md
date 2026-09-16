# SSH 首次搭建与复用

采用本地 OpenSSH，不部署 SSH MCP，不把私钥、密码或 OpenAI 凭据放上计算服务器。连接认证、用户目录授权、宿主运行时审批是三个独立层次。登录成功不等于允许提交计算。

## 默认使用独立终端向导

首次设置使用 [onboard.py](../scripts/onboard.py)，Windows 通过 [onboard.ps1](../scripts/onboard.ps1) 包装。不要再让用户逐段复制建钥、传公钥和 ssh-add 命令。向导运行在实际用户的独立原生终端；不在 agent 捕获输出的 exec/PTY 会话内启动向导，不截图、读终端或开转录。运行前检查本地 Python/OpenSSH 客户端是否可用；不需要启用 sshd 服务。

第一步选择语言：1 中文（默认）、2 English；此后向导选项、默认值说明、状态及结束提示采用所选语言。OpenSSH/操作系统自身的交互与诊断保留系统原文，向导提前解释 password、passphrase 和主机指纹的含义。语言仅用于本次窗口，不自动写入私人偏好。

每个选项明确显示回车行为；无安全通用值的字段标为必填，不伪造服务器事实。输入非法 y/n 时重新提示，必填字段空回车不会直接退出。

| 选项 | 默认与适用条件 |
|---|---|
| 网络与可信指纹已准备好 | n，需实际准备好后明确输入 y；不自动确认事实 |
| 本机别名 | vasp-server，多台服务器可自定义不同别名 |
| 复用已有 config | n，首次配置自动创建；已有可信文件时选 y |
| config / 密钥路径 | 当前用户常用路径；密钥由别名区分，不填正文 |
| 地址 / 登录用户名 | 无默认，必须填写服务器真实值 |
| SSH 端口 | 22；站点端口或隧道映射不同时修改 |
| 门户 / 管理员登记 | n；仅站点明确要求时选 y，且实际完成后输入 registered |
| 自动追加服务器公钥 | y；站点允许本人自行登记时适用，保留既有条目 |
| 启动 Windows ssh-agent | y；服务不可用时询问，仍需系统 UAC 确认 |
| 失败后继续引导 | y；最多两次，不能绕过主机信任或站点策略 |
| 密码 / 密钥口令 / 新主机信任 | 无代填密码；建议有口令密钥；新主机默认不信任，实际匹配独立指纹后才输入 yes |

用户要求弹窗时，先解析当前技能的绝对脚本路径和已安装 Python 路径，再用如下方式打开可见窗口。只传脚本/解释器路径，不传实际地址、账号或秘密；路径中的双引号应拒绝。不要加 ExecutionPolicy Bypass，不改系统执行策略。若策略阻止脚本，用户可在自己的终端直接运行 Python 入口。没有隔离的弹窗能力时说明限制，提供同一入口让用户本地运行。

```powershell
# 用户参数区：替换为本次实际技能路径与已发现的 Python 路径。
$WizardPath = 'ABSOLUTE_SKILL_PATH\scripts\onboard.ps1'
$PythonPath = 'ABSOLUTE_PYTHON_PATH\python.exe'
Start-Process powershell.exe -WindowStyle Normal -ArgumentList @(
    '-NoProfile', '-File', ('"{0}"' -f $WizardPath), '-Python', ('"{0}"' -f $PythonPath)
)
```

Linux/macOS 在用户自己的终端运行 `python3 -B ABSOLUTE_SKILL_PATH/scripts/onboard.py`。已有 desktop agent/keychain 优先复用；若没有，向导会说明如何在同一个 shell 启动 agent 后重跑，不偷偷创建生命周期不明的后台 agent。Windows 缺少 ssh-agent 时，向导先解释，再让用户在原窗口选择是否通过 UAC 启动固定的服务辅助器；只设置本机 ssh-agent 为 Manual 并启动，绝不启用 sshd、修改防火墙或服务器 sshd_config。

### 向导负责的完整链路

1. 用户在本地确认 VPN/隧道就绪，并持有管理员或控制台提供的主机指纹。地址、端口、用户名、别名和密钥路径只在该窗口录入。私密输入仅由 `ssh`、`ssh-keygen`、`ssh-add` 接收；不用 input/Read-Host、参数、环境变量、剪贴板或临时文件收集密码/口令/OTP。
2. 新直连配置创建专用 Ed25519 密钥，要求用户在原生提示中设置口令。已有密钥不覆盖；用 `ssh-keygen -y` 导出公钥，校验 `.pub` 配对；缺失公钥可重建，错配则明确停止并保留文件。已存在配置/密钥不会被静默覆盖。
3. 新配置单独保存在实际用户 `.ssh/vaspflow/<alias>.conf`，不修改其主 config；后续必须带该 `-F`/`--config` 路径。已有别名或跳板机选择“复用可信 config”分支，保留站点配置；修复时向导仅在用户窗口内用 `ssh -G` 解析 IdentityFile，不向 agent 传回结果，避免再次选错密钥路径。新跳板机需要先取得站点配置并验证每一跳，不能猜测或把私钥复制到跳板机。没有密码初始登录方式的新账号，向导会在首次登录前引导完成门户/管理员公钥登记。
4. 原生 SSH 显示新主机指纹，用户只在与独立来源一致时接受。`StrictHostKeyChecking=ask` 仅用于这一步，后续为 `yes`。`ssh-keyscan` 不是独立可信来源；指纹变化不自动删除或替换 known_hosts。
5. 登录后，在同一窗口询问公钥登记方式：门户/管理员登记，或明确同意向本人 `~/.ssh/authorized_keys` 追加。默认新增 `restrict` 条目；已有同一 key blob 的条目保留原有限制，不追加一个更宽松副本。辅助脚本拒绝符号链接、硬链接、错误所有者、组/其他用户可写路径和 root 账号；不递归 chmod、不改 home 权限、不覆盖授权文件。站点改用其他 AuthorizedKeysFile/集中目录、旧 sshd 不支持 restrict、或权限异常时交由站点管理流程处理。
6. 门户分支只展示公钥，不自动上传，必须在实际完成站点登记后输入 `registered`；直接回车不能充当已登记。能用密码登录且站点允许自行登记时，门户问题选 n，再同意自动追加公钥。原生 ssh-add 只在本机加载密钥。最后建立一个新的 SSH 连接，禁用连接复用，以 `BatchMode=yes` 和仅公钥认证验证，禁止密码/keyboard-interactive 回退。密码登录通过、公钥上传通过、ssh-add 通过分别不代表此项通过。
7. 失败时仍在原窗口解释密钥、agent、配置、门户、MFA 等分支，最多两次用户选择的修复尝试。认证失败不会自动反复输密码或无限重试。成功只向 agent 反馈别名、config 路径和公钥非交互验证状态；失败不要自动上传原始日志。

新配置会保留实际 host/user/路径在用户本机。脚本不自动生成含这些信息的 agent 档案。弹窗和 SSH 别名只是减少披露，不是防本机管理员、恶意软件或企业审计的隔离；不关闭审计。常规远程路径与程序输出仍可能含用户名，需要按任务处理。

## 本地故障处理边界

| 现象 | 向导或后续处理 |
|---|---|
| 私钥存在但 `.pub` 缺失/不配对 | 缺失则由私钥导出；错配不覆盖，选择正确密钥对 |
| 密码能登录但公钥不能 | 完成公钥登记、确认 config 的 IdentityFile、加载 agent，然后新连接验证 |
| ssh-agent 不可用 | 原窗口提供固定 Windows 服务辅助器或 Unix shell agent 指引；没有管理员许可时不提权 |
| Permission denied / 远端权限异常 | 只检查本人 SSH 路径的类型、所有者、模式；不放宽权限、不 sudo；管理员修复策略问题 |
| REMOTE HOST IDENTIFICATION HAS CHANGED | 停止，向管理员核实；不删 known_hosts 来消除报错 |
| 站点强制 MFA | 记录交互登录可用、非交互未验证；遵守站点认证，不能宣称永久免交互 |
| 本地通过，Codex 执行环境失败 | 使用相同显式 config 路径并检查原用户 agent 可达性；通过平台正常审批，不复制私钥或放宽 ACL |

若 SSH 配置来自第三方，先在用户本地审阅：`Match exec`、`ProxyCommand`、`Include`、`KnownHostsCommand` 可以触发本地行为。`PermitLocalCommand=no` 不能禁用所有这些机制；不能将任意下载的 config 当成纯数据。

## 验证、目录授权与档案

`python -B ABSOLUTE_SKILL_PATH/scripts/probe.py ALIAS --config ABSOLUTE_CONFIG_PATH` 默认只输出成功/失败，丢弃远端 stdout/stderr。它证明该执行环境能非交互认证，不证明具体认证机制或工具可用；向导的最终检查另外限定公钥认证。用户同意详细输出后，才加 `--details` 输出用户名、主机名、home 和 PATH 工具清单。非登录 PATH 缺失不表示未安装。

登录后取得实际工作目录读写范围，验证 canonical path、OS 权限和配额。只在已许可的新测试目录内做小文件上传/回读/哈希验收，清理仅本次测试文件。保存私人档案时，alias_only 模式的 host/user/port/identity_file/proxy_jump/指纹为 null，真实值由 OpenSSH 管理；保存别名、config 路径和实际验证结果。旧 raw 档案由用户本地脱敏，不先读出再声称未披露。

首次工作范围及后续计算提交复用实际授权，不重复询问相同范围；新批次仍需具体文件和资源预算。档案只是授权记录，不能实现 OS 级隔离。不要为免提示保存任意 SSH/Python 通行规则。

## 撤销

停止使用相应档案，撤销对应平台规则；撤销服务器登录时仅删除该专用公钥的准确条目，保留其他用户/设备的 key。`ssh-add -d KEY_PATH` 仅卸载该身份；不执行 `ssh-add -D` 清除所有身份。不要删除整个 known_hosts 或 authorized_keys。
