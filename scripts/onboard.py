"""Run ONLY in the user's separate native terminal, never a captured tool session."""

import base64
import ipaddress
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from probe import ssh_command

# User-adjustable defaults. No actual server settings belong in this script.
CONNECT_SECONDS = 15
INTERACTIVE_SECONDS = 600
CHECK_SECONDS = 45
MAX_REPAIR_ATTEMPTS = 2
SSH_DIR = Path.home() / ".ssh"
DEFAULT_ALIAS = 'vasp-server'
DEFAULT_PORT = '22'
LANGUAGE = 'zh'


def tr(zh, en):
    return zh if LANGUAGE == 'zh' else en


def choose_language():
    global LANGUAGE
    print('请选择语言 / Choose language: 1. 中文（默认 / default）  2. English')
    while True:
        choice = input('输入 1 或 2，回车选中文 / Enter 1 or 2; Enter defaults to Chinese: ').strip().lower() or '1'
        if choice in ('1', 'zh', '中文', '2', 'en', 'english'):
            LANGUAGE = 'zh' if choice in ('1', 'zh', '中文') else 'en'
            return
        print('请输入 1 或 2 / Please enter 1 or 2.')


def ask(label, default="", *, explanation="", required=False):
    if explanation:
        print(tr('说明：', 'Help: ') + explanation)
    hint = tr(f'默认：{default}；直接回车采用', f'Default: {default}; press Enter to use it') if default else (
        tr('无默认值，必须填写', 'No default; required') if required else tr('默认：留空，不确认', 'Default: blank; no confirmation'))
    while True:
        value = input(f'{label} [{hint}]: ').strip() or default
        if value or not required:
            return value
        print(tr('此项不能从通用设置推断，请填写实际值。', 'This value cannot be inferred. Please enter your actual setting.'))


def yes(label, default=False, *, explanation=""):
    while True:
        answer = ask(label + tr('（y=是，n=否）', ' (y=yes, n=no)'), 'y' if default else 'n', explanation=explanation).lower()
        if answer in ('y', 'yes', '是'):
            return True
        if answer in ('n', 'no', '否'):
            return False
        print(tr('请输入 y 或 n，也可以直接回车采用显示的默认项。', 'Enter y or n, or press Enter to use the displayed default.'))


def token(value, pattern, name):
    if not re.fullmatch(pattern, value):
        raise ValueError(tr(f'{name} 格式无效；请勿输入引号、命令或空白字符。', f'Invalid {name}; do not enter quotes, commands or whitespace.'))
    return value


def safe_path(value):
    # OpenSSH expands % tokens and ${variables}, even inside quoted config values.
    if any(ord(c) < 32 or c in '"%$' for c in value):
        raise ValueError(tr('路径包含 OpenSSH 展开符或控制字符。', 'Path contains an OpenSSH expansion or control character.'))
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(tr('请使用绝对路径。', 'Use an absolute path.'))
    for component in (path, *path.parents):
        if component.is_symlink() or getattr(component, 'is_junction', lambda: False)():
            raise ValueError(tr('请使用不含符号链接或目录联接的本机路径。', 'Use a local path without symbolic links or junctions.'))
    return path


def native(argv, **kwargs):
    # stdin/stderr stay attached to the real terminal unless PUBLIC key data is piped.
    return subprocess.run(argv, timeout=INTERACTIVE_SECONDS, check=True, **kwargs)


def public_identity(text):
    fields = text.strip().split()
    if len(fields) < 2:
        raise ValueError(tr('公钥格式无效。', 'Invalid public key.'))
    kind, blob = fields[:2]
    token(kind, r'ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(?:256|384|521)', 'key type')
    raw = base64.b64decode(blob, validate=True)
    length = int.from_bytes(raw[:4], 'big')
    if raw[4:4 + length] != kind.encode('ascii'):
        raise ValueError(tr('公钥类型与编码不匹配。', 'Public key type/encoding mismatch.'))
    return f'{kind} {blob}'


def prepare_key(key):
    key = safe_path(str(key))
    key.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    pub = safe_path(str(key) + '.pub')
    if not key.exists():
        if pub.exists():
            raise ValueError(tr('只有公钥、没有私钥。请选择新路径；已有文件不会被覆盖。', 'Public key exists without private key. Choose a new path; nothing overwritten.'))
        print(tr('即将创建专用密钥。Enter passphrase 是新密钥的保护口令，不是服务器密码。', 'Creating a dedicated key. Enter passphrase means a NEW key protection passphrase, not your server password.'))
        print(tr('口令无默认值；建议设置并妥善保存。原生程序允许空口令，但不推荐。第二次提示请重复输入。', 'No default passphrase. Set and keep one securely; an empty passphrase is allowed by OpenSSH but not recommended. Repeat it at the second prompt.'))
        native(['ssh-keygen', '-t', 'ed25519', '-f', str(key), '-C', 'vaspflow'])
    if not key.is_file():
        raise ValueError(tr('私钥必须是普通文件。', 'Private key must be a regular file.'))
    if os.name != 'nt' and key.stat().st_mode & 0o077:
        raise ValueError(tr('私钥权限过于宽松；请先在本机修复。', 'Private key permissions are too open; repair locally before continuing.'))
    print(tr('正在核对公私钥是否配对。若提示 Enter passphrase，请输入这把私钥的保护口令；无默认值。', 'Checking the key pair. If asked for Enter passphrase, enter this private key protection passphrase; there is no default.'))
    derived = public_identity(native(['ssh-keygen', '-y', '-f', str(key)], stdout=subprocess.PIPE).stdout.decode('ascii'))
    if pub.exists():
        if public_identity(pub.read_text(encoding='ascii')) != derived:
            raise ValueError(tr('.pub 与这把私钥不配对。请选择正确的密钥对；两个文件均保留。', 'The .pub file does NOT match this private key. Choose the correct pair; neither file changed.'))
    else:
        with pub.open('x', encoding='ascii', newline='\n') as stream:
            stream.write(derived + '\n')
    return derived


def config_text(alias, host, port, user, key, known_hosts):
    token(alias, r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', 'alias')
    if ':' in host:
        ipaddress.IPv6Address(host)
    else:
        token(host, r'[A-Za-z0-9][A-Za-z0-9._-]*', 'host')
    token(user, r'[A-Za-z0-9_][A-Za-z0-9_.-]*', 'username')
    if not 1 <= port <= 65535:
        raise ValueError(tr('端口必须在 1 到 65535 之间。', 'Port must be between 1 and 65535.'))
    return (f'Host {alias}\n    HostName {host}\n    User {user}\n    Port {port}\n'
            f'    IdentityFile "{safe_path(str(key)).as_posix()}"\n'
            f'    UserKnownHostsFile "{safe_path(str(known_hosts)).as_posix()}"\n'
            '    IdentitiesOnly yes\n    StrictHostKeyChecking yes\n'
            '    ForwardAgent no\n    ForwardX11 no\n    ClearAllForwardings yes\n'
            '    PermitLocalCommand no\n    ControlMaster no\n    ControlPath none\n'
            f'    ConnectTimeout {CONNECT_SECONDS}\n    ServerAliveInterval 15\n'
            '    ServerAliveCountMax 2\n')


def connection(alias, config, *, batch=False, first=False):
    argv = ssh_command(alias, config)[:-3]
    # Replace BatchMode/StrictHostKeyChecking in-place; first obtained SSH value wins.
    argv[argv.index('BatchMode=yes')] = 'BatchMode=yes' if batch else 'BatchMode=no'
    argv[argv.index('StrictHostKeyChecking=yes')] = 'StrictHostKeyChecking=ask' if first else 'StrictHostKeyChecking=yes'
    if batch:
        argv += ['-o', 'PreferredAuthentications=publickey', '-o', 'PasswordAuthentication=no',
                 '-o', 'KbdInteractiveAuthentication=no']
    return argv + [alias]


def batch_check(alias, config):
    result = subprocess.run(connection(alias, config, batch=True) + ['true'],
                            timeout=CHECK_SECONDS, stdin=subprocess.DEVNULL, check=False)
    return result.returncode == 0


def load_agent(key):
    result = subprocess.run(['ssh-add', '-l'], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=CHECK_SECONDS)
    if result.returncode == 2:
        if os.name != 'nt':
            print(tr('请启动或复用桌面 SSH agent，然后在继承 SSH_AUTH_SOCK 的终端重运行向导。', 'Start/reuse your desktop SSH agent, then rerun from a terminal inheriting SSH_AUTH_SOCK.'))
            print(tr('新 shell 会话可运行 eval "$(ssh-agent -s)"，然后在同一 shell 中重运行向导。', 'For a new shell session: eval "$(ssh-agent -s)"; then rerun this wizard in that shell.'))
            return False
        print(tr('Windows ssh-agent 不可用；它是本机客户端服务，不是 sshd 服务器服务。', 'Windows ssh-agent is unavailable. This client service is different from the sshd server.'))
        if not yes(tr('是否启用并启动本机 ssh-agent 服务', 'Enable and start the local ssh-agent service'), default=True,
                   explanation=tr('多数 Windows 用户选 y：用于记住已解锁的密钥；会出现系统 UAC 确认。选 n 则不修改服务，可能无法完成非交互登录。', 'Most Windows users choose y to keep the unlocked key available. A UAC prompt will appear. Choose n to leave the service unchanged; unattended login may remain unavailable.')):
            return False
        helper = Path(__file__).with_suffix('.ps1')
        # The only interpolation is a locally installed script path, escaped as a PS literal.
        literal = str(helper).replace("'", "''")
        command = ("$p = Start-Process powershell.exe -Verb RunAs -Wait -PassThru "
                   "-ArgumentList ('-NoProfile -File \"' + '" + literal +
                   "' + '\" -EnableAgent'); exit $p.ExitCode")
        native(['powershell.exe', '-NoProfile', '-Command', command])
    print(tr('即将加载本机密钥。Enter passphrase 仍是密钥保护口令，无默认值，不是服务器密码。', 'Loading your local key. Enter passphrase is the key protection passphrase, with no default; it is not your server password.'))
    native(['ssh-add', str(key)])
    return True


def register_via_portal(public):
    print(tr('此分支不会上传公钥。请先在服务器指定的门户登记，或请管理员登记以下公钥：', 'This branch does NOT upload the public key. Register the following key in the site portal or ask the administrator to register it:'))
    print(public)
    if ask(tr('实际登记完成后输入 registered', 'Enter registered after actual registration is complete'),
           explanation=tr('无自动确认：默认留空表示尚未登记并返回。只有在门户/管理员实际完成登记后才输入 registered。', 'No automatic confirmation. Blank means registration is not confirmed. Enter registered only after the portal or administrator has actually registered it.')) != 'registered':
        raise ValueError(tr('门户登记尚未确认。能用密码登录且站点允许自行登记时，请在门户问题选 n，再同意自动追加公钥。', 'Portal registration is not confirmed. If password login and self-registration are allowed, choose n for the portal question, then agree to automatic key registration.'))


def repair(alias, config, key=None, public=None):
    if key is None:
        # Local-only resolution of the user's trusted config; never return this inventory to Codex.
        resolved = native(connection(alias, config)[:-1] + ['-G', alias], stdout=subprocess.PIPE)
        identities = [safe_path(line.split(' ', 1)[1]) for line in resolved.stdout.decode('utf-8').splitlines()
                      if line.startswith('identityfile ') and line != 'identityfile none']
        if len(identities) == 1:
            key = identities[0]
            print(tr(f'使用本机 config 已指定的密钥：{key}', f'Use the key already selected by this local config: {key}'))
        else:
            key = safe_path(ask(tr('选择此配置中已指定的私钥绝对路径', 'Absolute path of a private key referenced by this config'),
                                str(next((p for p in identities if p.is_file()), SSH_DIR / f'id_ed25519_{alias}')),
                                explanation=tr('默认优先选配置中已存在的密钥；通常直接回车。只有明确要使用另一把已配置密钥时才修改。', 'The default prefers an existing key referenced by this config; usually press Enter. Change it only to select another configured key.')))
            if key not in identities:
                raise ValueError(tr('所选密钥未在该 config 的 IdentityFile 中指定，请选择已配置密钥；未登记其他密钥。', 'Selected key is not an IdentityFile in this config. Select a configured key; no unrelated key is registered.'))
    if public is None:
        public = prepare_key(key)
    print(tr('只有公钥会发送到服务器，私钥保留在本机。', 'Only this PUBLIC key may be sent to the server. Private key remains on this PC.'))
    print(tr('接下来是把公钥登记到服务器；ssh-add 只把密钥加载到本机，不能代替服务器登记。', 'Next, register the public key ON THE SERVER. ssh-add loads the key locally and does not register it on the server.'))
    if yes(tr('管理员是否要求通过专用门户或人工登记公钥', 'Does the administrator require portal or manual key registration'), default=False,
           explanation=tr('普通密码登录服务器通常选 n，下一步可自动登记。只有管理员明确要求时选 y；门户分支不会自动上传。', 'For ordinary password-login servers, choose n for automatic registration next. Choose y only if required by the administrator; the portal branch does not upload the key.')):
        register_via_portal(public)
    elif yes(tr('是否自动追加此公钥到本人服务器 ~/.ssh/authorized_keys', 'Automatically append this public key to your own server ~/.ssh/authorized_keys'), default=True,
             explanation=tr('允许自行登记的普通服务器推荐 y。只追加公钥并保留已有条目；SSH 可能提示输入服务器登录密码（无默认值）。选 n 跳过，未登记的新密钥将不能用于登录。', 'Choose y when the site permits self-registration. Existing entries are preserved. SSH may ask for the server login password (no default). Choose n to skip; an unregistered new key cannot authenticate.')):
        script = Path(__file__).with_name('install_public_key.sh').read_text(encoding='utf-8')
        native(connection(alias, config) + ['sh -c ' + shlex.quote(script)],
               input=(public + '\n').encode('ascii'))
    else:
        print(tr('已跳过登记；仍可检查此前已登记的密钥。', 'Registration skipped; checking an already registered key is still possible.'))
    return load_agent(key)


def main():
    if not sys.stdin.isatty():
        raise ValueError(tr('请打开独立的原生终端；不支持在捕获输出或非交互会话中配置。', 'Open a separate native terminal; captured/noninteractive onboarding is not supported.'))
    choose_language()
    for tool in ('ssh', 'ssh-keygen', 'ssh-add'):
        if not shutil.which(tool):
            raise ValueError(tr(f'未找到 {tool}。请先启用系统 OpenSSH 客户端，无需 sshd。', f'{tool} is missing. Enable the OS OpenSSH client first; no sshd needed.'))
    print(tr('VASPFlow 本机 SSH 配置向导：密码、口令、私钥不要粘贴到聊天中。', 'VASPFlow local SSH wizard: do not paste passwords, passphrases or private keys into chat.'))
    print(tr('每项均显示默认值与说明；直接回车采用默认项。地址/账号必须填写，口令由原生 OpenSSH 接收。', 'Every option shows its default and help. Enter uses the default. Host/account are required; native OpenSSH handles passwords and passphrases.'))
    print(tr('常见流程：新建配置 n → 门户 n → 自动登记 y。Ctrl+C 可停止。', 'Common choices: reuse config n -> portal n -> automatic registration y. Ctrl+C stops setup.'))
    if not yes(tr('网络/VPN/隧道已就绪，并已取得新主机的可信指纹', 'Network/VPN/tunnel ready and a trusted fingerprint available for each new host'), default=False,
               explanation=tr('这是实际状态确认，不能自动假定。准备好后明确输入 y；默认 n 暂停，不连接。无需 VPN 的直连服务器只需网络可达。指纹向管理员或服务器控制台核实。', 'This is a factual confirmation. Enter y only when ready; default n stops without connecting. Direct servers may not need a VPN. Verify fingerprints with the administrator or server console.')):
        print(tr('尚未开始配置：此项选择了 n（直接回车也是 n）。本轮没有生成 config、创建密钥或连接服务器。准备好后重新运行，在此项输入 y 才会继续。', 'Setup has not started: n was selected (Enter also means n). This run has not generated a config, created a key or connected. Rerun when ready and enter y here to continue.'))
        return 1
    alias = token(ask(tr('本机 SSH 别名', 'Local SSH alias'), DEFAULT_ALIAS,
                      explanation=tr('仅用于在本机称呼这台服务器，不是服务器地址或用户名。多数用户直接回车；多台服务器可用不同名称，例如 vasp-gpu。', 'A local nickname, not the server address or username. Usually press Enter; use distinct aliases such as vasp-gpu for multiple servers.')),
                  r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', 'alias')
    new_key = new_public = None
    if yes(tr('是否使用已有的可信 SSH config 文件', 'Use an existing trusted SSH config file'), default=False,
           explanation=tr('首次配置或没有 config 文件时选 n，向导会自动创建专用配置。仅已有可用配置（含跳板机配置）时选 y。', 'For first setup or no config file, choose n to create a dedicated config automatically. Choose y only for an existing working config, including jump-host settings.')):
        config = safe_path(ask(tr('已有 SSH config 的绝对路径', 'Absolute path of the existing SSH config'), str(SSH_DIR / 'config'),
                               explanation=tr('默认是当前用户常见的 .ssh/config。此处必须选择实际存在且可信的文件；没有该文件应使用新建分支，不要创建空文件。', 'Default is your usual .ssh/config. Select a real, trusted file. If it does not exist, use the new-config branch; do not create an empty file.')))
        # Includes, Match exec and ProxyCommand can execute local code. Only the user selects this file.
        print(tr('只选择自己的可信 config；向导不会重写已有连接设置。', 'Use only your own trusted config. The wizard does not rewrite existing connection settings.'))
    else:
        print(tr('正在配置直连。需要 ProxyJump 时，请选择站点提供的可信 config 并使用复用分支。', 'New direct connection. For ProxyJump use a site-provided trusted config and the reuse branch.'))
        folder = safe_path(str(SSH_DIR / 'vaspflow'))
        config = safe_path(str(folder / f'{alias}.conf'))
        if config.exists():
            print(tr('此别名的专用配置已存在，继续使用且不改写。', 'A dedicated config already exists for this alias; resuming it without changes.'))
        else:
            host = ask(tr('服务器地址或 IP', 'Server hostname or IP address'), required=True,
                       explanation=tr('无通用默认值，请填管理员提供的真实地址；只填域名或 IP，不加 ssh、用户名或端口。IPv6 不加方括号。', 'No universal default. Enter the real hostname or IP from your administrator, without ssh, username or port. IPv6 must not include brackets.'))
            port = int(ask(tr('SSH 端口', 'SSH port'), DEFAULT_PORT,
                           explanation=tr('常见 SSH 默认端口是 22，通常直接回车。管理员提供其他端口或使用端口映射时，填写实际端口。', 'The usual SSH port is 22; normally press Enter. Use the actual port if your administrator or tunnel mapping specifies another one.')))
            user = ask(tr('服务器登录用户名', 'Server login username'), required=True,
                       explanation=tr('无通用默认值，请填服务器上的普通计算账号；不是自动采用本机 Windows 用户名，也不是 root。', 'No universal default. Enter your regular server calculation account, not automatically your Windows username and not root.'))
            if user == 'root':
                raise ValueError(tr('请使用非 root 的计算账号。', 'Use a non-root calculation account.'))
            key = safe_path(ask(tr('本机私钥保存路径', 'Local private key path'), str(SSH_DIR / f'id_ed25519_{alias}'),
                                explanation=tr('多数用户直接回车：在本人 .ssh 目录保存该别名的专用密钥。不存在会新建，存在会校验并复用；这里不要粘贴密钥正文。', 'Usually press Enter: a dedicated key is stored in your .ssh directory for this alias. Missing keys are created; existing keys are checked and reused. Do not paste key contents here.')))
            content = config_text(alias, host, port, user, key, SSH_DIR / 'known_hosts')
            new_public = prepare_key(key)
            new_key = key
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            with config.open('x', encoding='utf-8', newline='\n') as stream:
                stream.write(content)
            if os.name != 'nt':
                config.chmod(0o600)
            print(tr('专用 config 已保存；原 .ssh/config 未改动。后续使用显示的 -F 配置路径。', 'Dedicated config saved. Existing ~/.ssh/config unchanged; always use the displayed -F path.'))
    print(tr('本次选用的 SSH config 路径（尚未验证登录）：', 'Selected SSH config path (login not yet verified): ') + str(config))
    portal_done = False
    if new_key is not None and yes(tr('首次登录前是否必须先经门户或管理员登记公钥', 'Must a portal or administrator register the key BEFORE the first login'), default=False,
                                  explanation=tr('大多数能用密码首次登录的服务器选 n。只有服务器禁止密码初始登录、且管理员要求预先登记时才选 y。', 'Choose n if first login with a password is allowed. Choose y only if password bootstrap is prohibited and the administrator requires prior registration.')):
        register_via_portal(new_public)
        load_agent(new_key)
        portal_done = True
    print(tr('下面是原生 SSH 提示：首次出现 Are you sure... 时默认不信任；只有指纹与管理员/控制台提供的一致，才输入完整 yes。', 'Native SSH prompts follow. Are you sure... defaults to no trust. Type the full word yes only after matching the administrator/console fingerprint.'))
    print(tr('若出现 password，请输入服务器登录密码（无默认值）；若出现 passphrase，请输入本机密钥保护口令（无默认值）。输入不回显属于正常现象。', 'password means the server login password; passphrase means the local key protection passphrase. Neither has a default. Hidden input is normal.'))
    print(tr('主机指纹变化时停止核实，不能删除 known_hosts 来消除警告。', 'Stop and verify a changed host fingerprint. Do not delete known_hosts to silence a warning.'))
    native(connection(alias, config, first=True) + ['true'])
    if new_key is not None and not portal_done:
        print(tr('继续本窗口配置：登记所选公钥，再在 ssh-agent 中解锁。', 'Continue setup here: register the selected public key, then unlock it in ssh-agent.'))
        try:
            repair(alias, config, new_key, new_public)
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            print(tr(f'本机登记/agent 步骤尚未完成：{exc}', f'Local registration/agent step incomplete: {exc}'))
            print(tr('继续下方引导检查；不会移除密钥或安全策略。', 'Continue with the guided check below; no key or security policy is removed.'))
    print(tr('交互登录已通过。正在以新连接验证只允许公钥的非交互登录。', 'Interactive login verified. Now testing a NEW connection with public-key-only BatchMode.'))
    for attempt in range(MAX_REPAIR_ATTEMPTS + 1):
        if batch_check(alias, config):
            print(tr('验证通过：', 'VERIFIED: ') + f'alias={alias}; public_key_batch=yes')
            print(tr('SSH config 本机路径（用于 --config / -F）：', 'SSH config (local path for --config / -F): ') + str(config))
            print(tr('只向 Codex 返回别名、config 路径和此状态；没有启动计算任务。', 'Return only alias, config path and this status to Codex. No compute work was started.'))
            return 0
        print(tr('非交互验证失败。密码能登录不等于公钥登录成功。', 'Batch check failed. Password login alone is not key-login success.'))
        print(tr('请查看本地 SSH 报错：密钥/config 选择、agent、门户登记或强制 MFA 可能需要处理。', 'Check the local SSH error: wrong key/config, agent unavailable, key portal, or mandatory MFA.'))
        print(tr('自定义密钥要使用同一路径；复用 config 时请在本地核实 IdentityFile。', 'For a new custom key path, enter that SAME path below; for reused configs verify IdentityFile locally.'))
        if attempt == MAX_REPAIR_ATTEMPTS or not yes(tr('是否在当前窗口继续修复公钥登记或 agent', 'Continue repairing key registration or agent in this window'), default=True,
                                                    explanation=tr('首次配置失败通常选 y，继续引导而不重建密钥；选 n 结束。最多两次修复，主机身份或站点策略问题需先核实。', 'For initial setup, normally choose y to continue guidance using the same key. Choose n to stop. At most two repairs; verify host identity and site policy issues first.')):
            break
        try:
            repair(alias, config)
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            print(tr(f'本机修复已停止：{exc}', f'Local repair stopped: {exc}'))
            print(tr('已有密钥和权限均保留；请解决上述原因后再重试。', 'Existing keys/permissions are preserved. Resolve the stated cause before retrying.'))
    print(tr('非交互登录尚未通过验证。MFA/门户/agent 策略问题可能需要管理员处理，不要降低安全要求。', 'NOT VERIFIED for unattended use. MFA/portal/agent policy may require admin help; do not weaken it.'))
    return 1


if __name__ == '__main__':
    exit_code = 1
    try:
        exit_code = main()
    except (ValueError, OSError, subprocess.SubprocessError, KeyboardInterrupt, EOFError) as exc:
        print(tr(f'配置已在本机停止：{exc}', f'Setup stopped locally: {exc}'), file=sys.stderr)
    finally:
        if sys.stdin.isatty():
            try:
                input(tr('请保留上方结果。默认：按回车关闭本窗口。', 'Keep the result above. Default: press Enter to close this window.'))
            except (KeyboardInterrupt, EOFError):
                pass
    sys.exit(exit_code)
