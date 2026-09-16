#!/bin/sh
# Only called by the local onboarding wizard, after explicit key-install consent.
# Input: one validated public key. Never receives a password or private key.
set -eu
umask 077
fail() { printf '%s\n' "$1" >&2; exit 1; }
IFS= read -r key || fail 'Missing public key'
set -f
set -- $key
[ "$#" -eq 2 ] || fail 'Expected key type and base64 only'
kind=$1
blob=$2
case "$kind" in ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521) ;; *) fail 'Unsupported key type' ;; esac
case "$blob" in ''|*[!A-Za-z0-9+/=]*) fail 'Invalid public key encoding' ;; esac
uid=$(id -u)
[ "$uid" -ne 0 ] || fail 'Use a non-root calculation account'
check_owned() {
    [ ! -L "$1" ] || fail 'Refusing a symbolic link in SSH authorization paths'
    [ "$(stat -c %u -- "$1")" = "$uid" ] || fail 'SSH path is not owned by this account'
    mode=$(stat -c %a -- "$1")
    [ "$((0$mode & 022))" -eq 0 ] || fail 'SSH path is group/world writable; ask the owner/admin to repair it'
}
check_owned "$HOME"
if [ ! -e "$HOME/.ssh" ] && [ ! -L "$HOME/.ssh" ]; then
    mkdir -m 700 -- "$HOME/.ssh"
fi
check_owned "$HOME/.ssh"
[ -d "$HOME/.ssh" ] || fail '.ssh is not a directory'
auth="$HOME/.ssh/authorized_keys"
lock="$HOME/.ssh/.vaspflow-key-install.lock"
mkdir -m 700 -- "$lock" || fail 'Another install or a stale lock exists; inspect locally before retrying'
trap 'rmdir -- "$lock"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [ ! -e "$auth" ] && [ ! -L "$auth" ]; then
    (set -C; : > "$auth")
fi
check_owned "$auth"
[ -f "$auth" ] || fail 'authorized_keys is not a regular file'
[ "$(stat -c %h -- "$auth")" = 1 ] || fail 'Refusing a hard-linked authorized_keys'
# Preserve options/comments on existing identities; never append a less restricted duplicate.
if awk -v kind="$kind" -v blob="$blob" '
    /^[[:space:]]*#/ { next }
    { for (i=1; i<NF; i++) if ($i == kind && $(i+1) == blob) found=1 }
    END { exit !found }' "$auth"; then
    printf 'Public key already present; existing restrictions preserved.\n'
else
    printf '\nrestrict %s %s vaspflow\n' "$kind" "$blob" >> "$auth"
    printf 'Public key appended with forwarding/PTY/user-rc restrictions.\n'
fi
