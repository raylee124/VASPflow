"""Offline release check; reports locations, never suspected secret values."""
import json
from pathlib import Path
import re

# Public files are individually opted in through the root .gitignore.
ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'private key': r'-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----',
    'access token': r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})',
    'IPv4 address': r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])',
    'email address': r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',
    'personal absolute path': r'(?i)(?:[A-Z]:[\\/](?:Users|Documents and Settings)[\\/][\w.-]+|/(?:home|Users)/[\w.-]+)',
    'SSH fingerprint': r'SHA256:[A-Za-z0-9+/]{20,}',
}


def check():
    allow = {line[2:] for line in (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()
             if line.startswith('!/')}
    files = []
    for folder in ROOT.rglob('*'):
        rel = folder.relative_to(ROOT).as_posix()
        if rel == '.git' or rel.startswith('.git/'):
            continue  # Git history/identity must be inspected separately before publishing.
        if folder.is_symlink() or getattr(folder, 'is_junction', lambda: False)():
            raise ValueError('Link in release: ' + rel)
        if folder.is_file():
            files.append(folder)
    actual = {p.relative_to(ROOT).as_posix() for p in files}
    if actual != allow:
        raise ValueError('Unexpected or missing files; inspect release inventory locally')
    for path in files:
        raw = path.read_bytes()
        if b'\r' in raw:
            raise ValueError('Non-LF line endings: ' + path.relative_to(ROOT).as_posix())
        for number, line in enumerate(raw.decode('utf-8').splitlines(), 1):
            for label, pattern in PATTERNS.items():
                if re.search(pattern, line):
                    raise ValueError(f'{label}: {path.relative_to(ROOT).as_posix()}:{number}')
    profile = json.loads((ROOT / 'assets/profile.example.json').read_text(encoding='utf-8'))
    for key, value in profile.items():
        if key in ('connection_privacy', 'authorization', 'notes'):
            continue
        if value is not None and value != [] and value != {}:
            raise ValueError('Filled example profile field: ' + key)
    if profile['connection_privacy'] != 'alias_only':
        raise ValueError('Example privacy mode changed')
    for key, value in profile['authorization'].items():
        values = value.values() if isinstance(value, dict) else [value]
        if any(item is not None and item is not False for item in values):
            raise ValueError('Populated authorization: ' + key)
    prefs = json.loads((ROOT / 'assets/preferences.example.json').read_text(encoding='utf-8'))
    if prefs != {'schema_version': 1, 'memory_consent': {
            'enabled': False, 'confirmed_at': None, 'user_statement': None}, 'preferences': []}:
        raise ValueError('Populated preference template')
    print(f'PASS: {len(files)} public files; blank profiles, common privacy patterns and LF checked')


if __name__ == '__main__':
    check()
