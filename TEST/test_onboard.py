"""Offline behavior checks. No network, real credentials, agent changes or elevation."""
import base64
import contextlib
import io
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import onboard

# Language selection, displayed defaults, and invalid/required input behavior.
with contextlib.redirect_stdout(io.StringIO()), patch('builtins.input', return_value=''):
    onboard.choose_language()
    assert onboard.LANGUAGE == 'zh'
with contextlib.redirect_stdout(io.StringIO()), patch('builtins.input', side_effect=['invalid', '2']):
    onboard.choose_language()
    assert onboard.LANGUAGE == 'en'
with patch('builtins.input', return_value='') as prompt:
    assert onboard.ask('Port', '22') == '22'
    assert '22' in prompt.call_args.args[0]
    assert onboard.yes('Append key', default=True) is True
    assert onboard.yes('Use portal', default=False) is False
with contextlib.redirect_stdout(io.StringIO()), patch('builtins.input', side_effect=['', 'actual-account']):
    assert onboard.ask('Account', required=True) == 'actual-account'
with contextlib.redirect_stdout(io.StringIO()), patch('builtins.input', side_effect=['maybe', 'no']):
    assert onboard.yes('Continue', default=True) is False
onboard.LANGUAGE = 'zh'

# Enter at readiness must explain the stop, without reaching setup or SSH.
for language, expected in [('1', '尚未开始配置'), ('2', 'Setup has not started')]:
    output = io.StringIO()
    with patch.object(onboard.sys.stdin, 'isatty', return_value=True), \
         patch.object(onboard.shutil, 'which', return_value='tool'), \
         patch('builtins.input', side_effect=[language, '']) as inputs, \
         patch.object(onboard, 'prepare_key') as prepare, \
         patch.object(onboard, 'native') as remote, \
         patch.object(onboard, 'batch_check') as check, \
         contextlib.redirect_stdout(output):
        assert onboard.main() == 1
        assert inputs.call_count == 2 and expected in output.getvalue()
        prepare.assert_not_called()
        remote.assert_not_called()
        check.assert_not_called()
onboard.LANGUAGE = 'zh'


def rejects(call):
    try:
        call()
    except (ValueError, OSError):
        return
    raise AssertionError('Unsafe input was accepted')


kind = b'ssh-ed25519'
blob = base64.b64encode(len(kind).to_bytes(4, 'big') + kind + b'\x00\x00\x00\x20' + b'x' * 32).decode()
public = f'ssh-ed25519 {blob}'
assert onboard.public_identity(public + ' comment') == public
for bad in ('not a key', public.replace('ssh-ed25519', 'ssh-rsa'), 'ssh-ed25519 !!!'):
    rejects(lambda: onboard.public_identity(bad))

with tempfile.TemporaryDirectory(prefix='offline-', dir=ROOT / 'TEST') as folder:
    temp = Path(folder)
    key = temp / 'key with spaces'
    cfg = temp / 'synthetic config'
    known = temp / 'known hosts'
    cfg.write_text(onboard.config_text('test-alias', 'example.invalid', 22, 'example_user', key, known), encoding='utf-8')
    assert 'HostName ::1' in onboard.config_text('test-alias', '::1', 22, 'example_user', key, known)
    for value in ('host\nProxyCommand evil', '-bad', 'host;id', 'host%h'):
        rejects(lambda: onboard.config_text('test-alias', value, 22, 'user', key, known))
    for value in (0, 65536):
        rejects(lambda: onboard.config_text('test-alias', 'example.invalid', value, 'user', key, known))
    rejects(lambda: onboard.safe_path(str(temp / '%h')))
    rejects(lambda: onboard.safe_path(str(temp / '${HOME}')))
    rejects(lambda: onboard.safe_path('relative-key'))
    command = onboard.connection('test-alias', cfg, batch=True)
    assert command.count('BatchMode=yes') == 1 and 'BatchMode=no' not in command
    for option in ('PreferredAuthentications=publickey', 'PasswordAuthentication=no',
                   'KbdInteractiveAuthentication=no', 'ControlPath=none', 'StrictHostKeyChecking=yes'):
        assert option in command
    first = onboard.connection('test-alias', cfg, first=True)
    assert 'StrictHostKeyChecking=ask' in first and 'StrictHostKeyChecking=yes' not in first
    # Ask OpenSSH itself to parse ONLY this synthetic config, without connecting.
    if shutil.which('ssh'):
        parsed = subprocess.run(command[:-1] + ['-G', 'test-alias'], capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)
        assert 'hostname example.invalid' in parsed.stdout
        assert 'identitiesonly yes' in parsed.stdout
    key.write_text('synthetic private placeholder; never used by ssh', encoding='ascii')
    key.chmod(0o600)
    fake = subprocess.CompletedProcess([], 0, stdout=(public + '\n').encode())
    with patch.object(onboard, 'native', return_value=fake):
        assert onboard.prepare_key(key) == public
        pub = Path(str(key) + '.pub')
        assert pub.read_text().strip() == public
        original = key.read_bytes()
        pub.write_text('ssh-rsa AAAA wrong', encoding='ascii')
        rejects(lambda: onboard.prepare_key(key))
        assert key.read_bytes() == original and pub.read_text() == 'ssh-rsa AAAA wrong'
    # Existing working config must not trigger registration, key generation or UAC.
    with patch.object(onboard.sys.stdin, 'isatty', return_value=True), \
         patch.object(onboard, 'choose_language'), \
         patch.object(onboard.shutil, 'which', return_value='tool'), \
         patch.object(onboard, 'yes', side_effect=[True, True]), \
         patch.object(onboard, 'ask', side_effect=['test-alias', str(cfg)]), \
         patch.object(onboard, 'native') as run, \
         patch.object(onboard, 'batch_check', return_value=True), \
         patch.object(onboard, 'repair') as repair:
        assert onboard.main() == 0
        repair.assert_not_called()
        assert run.call_count == 1
    # A failing password-only connection cannot become a claimed batch success.
    with patch.object(onboard.sys.stdin, 'isatty', return_value=True), \
         patch.object(onboard, 'choose_language'), \
         patch.object(onboard.shutil, 'which', return_value='tool'), \
         patch.object(onboard, 'yes', side_effect=[True, True, True, True]), \
         patch.object(onboard, 'ask', side_effect=['test-alias', str(cfg)]), \
         patch.object(onboard, 'native'), \
         patch.object(onboard, 'batch_check', return_value=False) as check, \
         patch.object(onboard, 'repair') as repair:
        assert onboard.main() == 1
        assert repair.call_count == 2 and check.call_count == 3
    # New custom key must flow through registration automatically before the batch test.
    new_ssh = temp / 'new-ssh'
    custom_key = new_ssh / 'custom-key'
    with patch.object(onboard, 'SSH_DIR', new_ssh), \
         patch.object(onboard.sys.stdin, 'isatty', return_value=True), \
         patch.object(onboard, 'choose_language'), \
         patch.object(onboard.shutil, 'which', return_value='tool'), \
         patch.object(onboard, 'yes', side_effect=[True, False, False]), \
         patch.object(onboard, 'ask', side_effect=['new-alias', 'example.invalid', '22', 'user', str(custom_key)]), \
         patch.object(onboard, 'prepare_key', return_value=public), \
         patch.object(onboard, 'native'), \
         patch.object(onboard, 'batch_check', return_value=True), \
         patch.object(onboard, 'repair') as repair:
        assert onboard.main() == 0
        repair.assert_called_once_with('new-alias', new_ssh / 'vaspflow/new-alias.conf', custom_key, public)
        assert not (new_ssh / 'config').exists()
    with patch.object(onboard, 'native', return_value=subprocess.CompletedProcess([], 0,
              stdout=f'identityfile {key.as_posix()}\n'.encode())), \
         patch.object(onboard, 'prepare_key', return_value=public) as prepare, \
         patch.object(onboard, 'yes', side_effect=[False, False]), \
         patch.object(onboard, 'load_agent', return_value=True):
        assert onboard.repair('test-alias', cfg)
        prepare.assert_called_once_with(key)
    # Pressing Enter in the portal branch must not be mistaken for actual registration.
    with patch.object(onboard, 'yes', return_value=True), \
         patch.object(onboard, 'ask', return_value=''), \
         patch.object(onboard, 'native') as remote, \
         patch.object(onboard, 'load_agent') as agent:
        rejects(lambda: onboard.repair('test-alias', cfg, key, public))
        remote.assert_not_called()
        agent.assert_not_called()
    # Direct registration sends public key bytes to the fixed installer before agent loading.
    with patch.object(onboard, 'yes', side_effect=[False, True]), \
         patch.object(onboard, 'native') as remote, \
         patch.object(onboard, 'load_agent', return_value=True):
        assert onboard.repair('test-alias', cfg, key, public)
        remote.assert_called_once()
        assert remote.call_args.kwargs['input'] == (public + '\n').encode('ascii')
        assert 'authorized_keys' in remote.call_args.args[0][-1]
        assert 'StrictHostKeyChecking=yes' in remote.call_args.args[0]
    # Exercise the shipped shell scripts locally in isolated fake Linux-home/run dirs.
    # Run real default decisions in English: n for reuse/portal and y for append.
    english_output = io.StringIO()
    with patch.object(onboard, 'SSH_DIR', temp / 'english-ssh'), \
         patch.object(onboard.sys.stdin, 'isatty', return_value=True), \
         patch.object(onboard.shutil, 'which', return_value='tool'), \
         patch('builtins.input', side_effect=['2', 'y', '', '', 'example.invalid', '', 'example_user', '', '', '', '']) as inputs, \
         patch.object(onboard, 'prepare_key', return_value=public), \
         patch.object(onboard, 'native') as remote, \
         patch.object(onboard, 'load_agent', return_value=True), \
         patch.object(onboard, 'batch_check', return_value=True), \
         contextlib.redirect_stdout(english_output):
        assert onboard.main() == 0
        assert remote.call_count == 2  # initial login, then automatic registration
        assert remote.call_args.kwargs['input'] == (public + '\n').encode('ascii')
        assert all(call.args[0].isascii() for call in inputs.call_args_list[1:])
    assert all(line.isascii() for line in english_output.getvalue().splitlines()[1:])
    onboard.LANGUAGE = 'zh'
    bash = shutil.which('bash')
    if bash:
        def posix(path):
            path = str(path)
            if os.name == 'nt':
                cygpath = Path(bash).with_name('cygpath.exe')
                return subprocess.check_output([str(cygpath), '-u', path], text=True, encoding='utf-8', errors='replace').strip()
            return path

        for script in (ROOT / 'scripts/install_public_key.sh', ROOT / 'assets/run-direct.sh'):
            subprocess.run([bash, '-n', posix(script)], check=True)
        fakehome = temp / 'fakehome'
        fakehome.mkdir(mode=0o700)
        env = dict(os.environ, HOME=posix(fakehome))
        installer = [bash, posix(ROOT / 'scripts/install_public_key.sh')]
        result = subprocess.run(installer, input=(public + '\n').encode('ascii'), capture_output=True, env=env)
        # root is deliberately disallowed; other platforms must really execute the installer.
        if hasattr(os, 'geteuid') and os.geteuid() == 0:
            assert result.returncode != 0 and b'non-root' in result.stderr
        else:
            assert result.returncode == 0, result.stderr
            auth = fakehome / '.ssh/authorized_keys'
            first_content = auth.read_bytes()
            subprocess.run(installer, input=(public + '\n').encode('ascii'), capture_output=True, env=env, check=True)
            assert auth.read_bytes() == first_content
            restricted = f'command="false",restrict {public} old-device\n'
            auth.write_text(restricted, encoding='ascii')
            subprocess.run(installer, input=(public + '\n').encode('ascii'), capture_output=True, env=env, check=True)
            assert auth.read_text() == restricted
            lock = fakehome / '.ssh/.vaspflow-key-install.lock'
            lock.mkdir()
            result = subprocess.run(installer, input=(public + '\n').encode('ascii'), capture_output=True, env=env)
            assert result.returncode != 0 and auth.read_text() == restricted
            lock.rmdir()
            # A hard link must fail before altering the target.
            linked = temp / 'linked-authorizations'
            os.link(auth, linked)
            result = subprocess.run(installer, input=(public + '\n').encode('ascii'), capture_output=True, env=env)
            assert result.returncode != 0 and linked.read_text() == restricted
            linked.unlink()
        run_dir = temp / 'run'
        run_dir.mkdir()
        for name in ('INCAR', 'POSCAR', 'POTCAR'):
            (run_dir / name).write_text('synthetic test input\n')
        fake_mpi = temp / 'fake-mpirun'
        fake_mpi.write_text('#!/usr/bin/env bash\n[[ $1 = -np && $2 = 2 ]] || exit 9\necho fake-run\nexit 7\n', encoding='ascii', newline='\n')
        fake_mpi.chmod(0o700)
        runner = temp / 'run-direct.sh'
        content = (ROOT / 'assets/run-direct.sh').read_text()
        for name, value in dict(RUN_DIR=posix(run_dir), MPIEXEC=posix(fake_mpi),
                                VASP_EXECUTABLE=posix(fake_mpi), MPI_RANKS='2',
                                OMP_THREADS='1', MAX_SECONDS='10').items():
            content = content.replace(f"{name}=''", f'{name}={shlex.quote(value)}')
        runner.write_text(content, encoding='ascii', newline='\n')
        direct_env = dict(os.environ)
        if os.name == 'nt':
            # Rtools ps is not Linux procps. Stub only process metadata, not launch/locking.
            fake_ps = temp / 'ps'
            fake_ps.write_text('#!/usr/bin/env bash\necho synthetic-process-start\n', encoding='ascii', newline='\n')
            fake_ps.chmod(0o700)
            direct_env['PATH'] = str(temp) + os.pathsep + str(Path(bash).parent) + os.pathsep + direct_env['PATH']
        result = subprocess.run([bash, posix(runner)], capture_output=True, text=True, encoding='utf-8', errors='replace', env=direct_env)
        assert result.returncode == 7, (result.returncode, result.stderr,
            (run_dir / 'vasp.stderr.log').read_text() if (run_dir / 'vasp.stderr.log').exists() else '')
        assert (run_dir / '.vaspflow-started/exit-code').read_text().strip() == '7'
        output = (run_dir / 'vasp.stdout.log').read_bytes()
        result = subprocess.run([bash, posix(runner)], capture_output=True, text=True, encoding='utf-8', errors='replace', env=direct_env)
        assert result.returncode != 0 and (run_dir / 'vasp.stdout.log').read_bytes() == output
        locked_run = temp / 'locked-run'
        locked_run.mkdir()
        for name in ('INCAR', 'POSCAR', 'POTCAR'):
            (locked_run / name).write_text('synthetic\n')
        (locked_run / '.vaspflow-started').mkdir()
        runner.write_text(content.replace(posix(run_dir), posix(locked_run)), encoding='ascii', newline='\n')
        result = subprocess.run([bash, posix(runner)], capture_output=True, text=True, encoding='utf-8', errors='replace', env=direct_env)
        assert result.returncode == 3 and not (locked_run / 'vasp.stdout.log').exists()
        timed_run = temp / 'timed-run'
        timed_run.mkdir()
        for name in ('INCAR', 'POSCAR', 'POTCAR'):
            (timed_run / name).write_text('synthetic\n')
        fake_mpi.write_text('#!/usr/bin/env bash\nsleep 4\n', encoding='ascii', newline='\n')
        runner.write_text(content.replace(posix(run_dir), posix(timed_run)).replace('MAX_SECONDS=10', 'MAX_SECONDS=1'), encoding='ascii', newline='\n')
        result = subprocess.run([bash, posix(runner)], capture_output=True, text=True, encoding='utf-8', errors='replace', env=direct_env, timeout=10)
        assert result.returncode == 124
        assert (timed_run / '.vaspflow-started/exit-code').read_text().strip() == '124'
        print('PASS: real shell installer idempotence/restrictions/lock/hardlink; direct exit code and duplicate prevention')
    else:
        print('SKIP: shell integration requires bash; run this check on Linux before live acceptance')

print('PASS: config injection, key-pair protection, SSH parser, auth flags, resume and bounded failure')
