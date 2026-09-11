---
name: security-audit
description: Use when the user asks for a security audit or a check of OS configuration - "security audit", "check security", "do we have holes anywhere", "what is exposed to the outside", "open ports", "hardening check", "am I exposed" - or asks whether the machine is safe after opening it to the network, installing a server or container, or before handing it to someone else.
---

# Security audit

A read-only inspection of a running Linux system's configuration, focused on
**known holes in the setup**: accounts and authentication, remote access,
network exposure, outdated software, file permissions, kernel and LSM, services
and automation. The output is **a table of risks sorted by risk** — not a list
of everything that could be tightened.

**Two principles the whole skill rests on:**

1. **A finding without evidence from this machine is advice from the internet.**
   Every row of the table must have evidence from a specific command run here.
   "It is good practice to disable root login" is not a finding;
   `permitrootlogin yes` from `sshd -T` is.
2. **Threat model before checklist.** Risk = impact × reachability. Without an
   answer to *who would exploit this, and from where can they reach it*, you
   get an audit in which twenty harmless rows bury one real hole.

The audit **never fixes anything.** A fix is a separate task under CLAUDE.md §3a.

## Rules of engagement

| What | How |
|---|---|
| Read-only command without root | Run it right away, without asking. |
| Read-only command with root (`sshd -T`, `firewall-cmd`, `ss -p` over other users' processes, `/etc/shadow`, `sudoers`) | Collect them and present them for approval **as one block**. For this skill the root block is large — without it, half of the audit stays unanswered. |
| Any fix, even a trivial one | Always §3a: what / why / impact / rollback. Never as part of the audit. |

### Commands that look like auditing but change state

| Do not run | Why |
|---|---|
| `nmap`, `nikto` against anything | Scanning is an active intervention on the network, and against someone else's address also a legal problem. `ss` and `firewall-cmd` tell you the exposure more precisely. |
| `setenforce`, `firewall-cmd --add-*`, `systemctl stop` "just to test" | Testing by switching a protection off is a change, not diagnostics. |
| `dnf upgrade --security` | An update is a fix and needs approval. The audit only checks `dnf updateinfo`. |
| `chmod`/`chown` "because it's obvious" | The most obvious fix is still a fix. |
| `ssh-keygen -p`, changing a key's passphrase | Modifies the user's file. |
| `flatpak update`, `fwupdmgr update` | Changes state. The read-only forms are `--no-deploy` and `fwupdmgr get-updates` respectively. |

## Threat model — do not skip it

Before you build the table, determine **whom the machine is defending
against**. On a desktop behind NAT the answer differs from a server on a public
address, and it changes the severity of almost every finding.

| Attacker | Where they come from | What counts as a hole for them |
|---|---|---|
| Anyone on the internet | Port forwarded by the router, VPN, cloud service | Service listening on `0.0.0.0`, sshd with passwords, published container |
| Anyone on the same network (coffee shop, dorm, guests on Wi-Fi) | LAN, mDNS, Samba, printer | Shares without a password, VNC/RDP, `rpcbind`, an open firewall zone |
| Code the user runs themselves | Browser, package from npm/pip/cargo, game, AppImage, extension | Keys and tokens readable in home, `~/.docker/config.json`, membership in `docker`, agent without confirmation |
| A second local account | Logging in to the machine | World-writable files, SUID outside a package, unit running a script from home |
| Hardware thief | Physical access | Unencrypted disk, saved passwords, missing screen lock |

**Key rule for a single-user desktop:** the boundary is not `user` versus
`root`, but `user` versus the rest of the world. Whoever takes over the user's
account has their mail, keys, browser and backups — they no longer need root.
It follows that:

- "The user in `wheel` can become root via `sudo`" is **a description of the
  system design, not a finding.** The same goes for membership in `docker`,
  `libvirt`, `kvm` — it is R4, record it and move on. It becomes a finding only
  when someone else also has an account on the machine.
- Conversely, the finding "a process running as the user reads
  `~/.ssh/id_ed25519` without a passphrase and sends it out" is real, even
  though it has nothing to do with root.

For **every** finding, answer: *who would exploit this, and from where can they
reach it?* The answer goes into its own column of the table. A finding for which
you cannot write that answer does not belong in the table.

## What is not a finding

Per CLAUDE.md §6, the distribution default is not reported as a hole. Verify it
before you write the row: `rpm -V <package>` (or `dpkg -V`), or by confirming
that no custom configuration file exists at all.

| Looks like a hole | What it really is on a desktop |
|---|---|
| `avahi-daemon`, `cups`, `bluetoothd` running | Default state of the desktop edition. It becomes a finding only when they are reachable from a zone other than home. |
| Open port on `127.0.0.1` | Loopback is not exposure. The difference between `127.0.0.1` and `0.0.0.0` is the whole finding. |
| `unprivileged_userns_clone = 1` | Fedora and Debian have it enabled; Flatpak, podman and the browser sandbox depend on it. |
| Home directory `0755` | The distribution's default `UMASK`. R4 on a single-user machine. |
| OpenSSH version in the banner, replies to ping | Cosmetic. Hiding the version is not protection. |
| Recommendations from a CIS/DISA server profile | The profiles target servers. `noexec` on `/home`, blocking USB or disabling `avahi` on a machine that prints and transfers files is harm without gain. |
| Anything listed in `NOTES.md` under **Accepted risks** | The user has already decided it once. It goes into R4 as one summary row. |

## Procedure

### 0. Machine context

```bash
cat hosts/$(hostname)/facts.md hosts/$(hostname)/NOTES.md 2>/dev/null
ip -brief address; ip route get 1.1.1.1
```

Without the facts you cannot tell the right firewall, LSM or package manager.
From `ip`, find out whether the machine is behind NAT (address from 10/8,
172.16/12, 192.168/16) or directly on a public address — that shifts the
severity of the whole of phase 3 by one level.

In `NOTES.md`, look for the **Accepted risks** section (headings in host files
use the language from `hosts/sysadmin.toml`). Whatever is listed there is not
reported again as a finding.

### 1. Accounts and authentication

```bash
awk -F: '$3==0 {print "UID 0:", $1}' /etc/passwd
awk -F: '$3>=1000 && $3<65534 {print $1, $3, $7}' /etc/passwd
awk -F: '$3>0 && $3<1000 && $7 !~ /(nologin|false|sync|shutdown|halt)$/ {print "system account with shell:", $1, $7}' /etc/passwd
getent group wheel sudo adm docker libvirt kvm vboxusers
grep -E '^(PASS_MAX_DAYS|UMASK|ENCRYPT_METHOD)' /etc/login.defs
ls -la /etc/security/faillock.conf /etc/security/pwquality.conf 2>/dev/null
who; last -n 15
```

A second UID 0 in `/etc/passwd` is always R1 — it is a full root that alerts
nobody. A system account with an interactive shell is R3: a service that can be
exploited can then also log in.

Add to the root block: `/etc/shadow` (empty passwords), `sudo -l` and
`/etc/sudoers.d/` (`NOPASSWD: ALL` granted to everyone instead of for one
command).

### 2. Remote access

First find out whether anything is listening at all — for a machine without
`sshd` the honest answer is "not running", not a page of recommendations for
configuring it.

```bash
systemctl is-enabled sshd 2>/dev/null; systemctl is-active sshd
systemctl list-unit-files --state=enabled --no-pager \
  | grep -Ei 'ssh|vnc|rdp|krfb|smb|nmb|nfs|telnet|ftp|cockpit|rpcbind|tftp'
stat -c '%a %U %n' ~/.ssh ~/.ssh/* 2>/dev/null
for k in ~/.ssh/id_*; do case "$k" in *.pub|*'*') continue;; esac
  ssh-keygen -y -P '' -f "$k" >/dev/null 2>&1 && echo "KEY WITHOUT PASSPHRASE: $k"; done
grep -c '^\(ssh-\|ecdsa-\|sk-\)' ~/.ssh/authorized_keys 2>/dev/null
```

Read the effective sshd configuration **only from `sshd -T`, never from the
file** — between `sshd_config`, drop-ins in `sshd_config.d/`, `Include` and the
system-wide `crypto-policies` there are differences you will not notice when
reading the config file. `sshd -T` needs root, so it belongs in the block in
phase 8:

```bash
sudo sshd -T | grep -E '^(permitrootlogin|passwordauthentication|kbdinteractive|permitemptypasswords|x11forwarding|allowusers|allowgroups|port|listenaddress|maxauthtries)'
```

`permitrootlogin yes` plus `passwordauthentication yes` on a machine reachable
from the internet is R1, and there is no point in softening it. Behind NAT it is
R2 — exactly one thing stands in the way, and that is the router.

A key without a passphrase is rated by what it opens: a key to production is
R2, a key between two of your own machines in one room R4.

### 3. Exposure to the outside

This is the core of the audit. The goal is not a list of ports but, **for every
listening socket, an answer to three questions**: which process, on which
address, and does the firewall let traffic through to it.

```bash
ss -tulpn
ss -tulpnH | awk '{print $1, $5}' | sort -u
```

Without root you see processes only for your own sockets — the full mapping
belongs in the root block. A socket owned by someone else can still be
attributed via `/proc/net/tcp`: convert the port to hex and take the `uid`
column from its row. **`ss` is a snapshot, not an inventory.** D-Bus- and
socket-activated daemons (`passimd`) appear and disappear in it, so a port
missing from the previous run is not necessarily new — check
`rpm -q --qf '%{INSTALLTIME:date}'` and
`systemctl show <unit> -p ActiveEnterTimestamp` before reporting it as a change.
The address decides the severity:

| Address | Meaning |
|---|---|
| `127.0.0.1`, `[::1]` | This machine only. Not exposure. |
| `0.0.0.0`, `[::]`, `*` | All interfaces — reachable from everything the firewall lets through. |
| A specific interface address | Reachable from that network. Verify which one. |

```bash
firewall-cmd --get-default-zone; firewall-cmd --get-active-zones
firewall-cmd --list-all --zone="$(firewall-cmd --get-default-zone)"
nmcli -f NAME,DEVICE,TYPE,STATE connection show --active
```

Read-only `firewall-cmd` (`--list-all`, `--get-active-zones`, `--list-ports`)
works even without root — verified on Fedora 44. You need root only for
`/etc/firewalld/`. The zone of the active interface is what matters: a service
allowed in `public` means something different than in `home`. **Compare the
zone with the shipped version** in `/usr/lib/firewalld/zones/<zone>.xml` —
whatever is extra is a local addition, and that is the only part that is a
finding. Also find out which zone a **new** interface gets:
`firewall-cmd --get-default-zone` versus
`nmcli -g connection.zone connection show <profile>`. A profile without a zone
falls into the default one, and that tends to be looser than the one you have
on the cable.

**Containers bypass firewalld, and this is the most common silent hole on a
desktop.** Docker inserts its own nftables/iptables chains ahead of firewalld's
rules, so `docker run -p 5432:5432` exposes the database to the whole LAN even
though `firewall-cmd --list-ports` is empty.

```bash
docker ps --format '{{.Names}}\t{{.Ports}}\t{{.Image}}' 2>/dev/null
podman ps --format '{{.Names}}\t{{.Ports}}' 2>/dev/null
```

A publication in the form `0.0.0.0:5432->5432/tcp` is a finding.
`127.0.0.1:5432->5432/tcp` is not. It can be confirmed in the root block with
`sudo nft list chain ip filter DOCKER`.

### 4. Packages and updates

```bash
dnf updateinfo summary --available
dnf updateinfo list --security --available
dnf history list | head -5
rpm -qa --qf '%{INSTALLTIME}\t%{NAME}\n' | sort -rn | head -3
```

(On a dpkg-based distribution `apt list --upgradable` and `debsecan`, on Arch
`checkupdates` and `arch-audit` — derive it from `facts.md`.)

Compare the **distribution's end-of-support date** from `facts.md` with today's
date. A distribution past EOL no longer receives security fixes; that is R1
regardless of how well the machine is otherwise configured.

```bash
flatpak list --columns=application,branch,runtime,installation
flatpak list --runtime --columns=application,branch
```

A runtime on an old branch (`org.freedesktop.Platform` several versions back)
no longer receives fixes, and it carries the libraries of every application
built on it.

**Do not use `flatpak remote-ls --updates` as a source of findings.** It compares
against a stale local cache and reports updates that do not exist;
`flatpak update` fetches the current remote state first. Verify with
`flatpak update --no-deploy`, or compare `flatpak info <app>` with
`flatpak remote-info --cached <remote> <app>`. And tell two different things
apart: **an application that is behind** is a finding with a fix, whereas **an
up-to-date application on an old runtime** is the vendor's decision, which you
cannot do anything about on this machine — the proposal is then to keep it or
to uninstall it.

**Software outside the package manager never gets a security update** — that is
why it is searched for separately:

```bash
ls -la /opt /usr/local/bin /usr/local/lib 2>/dev/null
ls -la ~/.local/bin ~/Applications 2>/dev/null; find ~ -maxdepth 3 -name '*.AppImage' 2>/dev/null
pip list --user 2>/dev/null | tail -n +3 | wc -l; pipx list 2>/dev/null | head
ls ~/.cargo/bin ~/.npm-global/bin 2>/dev/null; npm ls -g --depth=0 2>/dev/null
```

Pay special attention to anything that talks over the network or processes
untrusted input: the browser, Electron applications, the VPN client, the media
player.

### 5. File permissions and integrity

```bash
find /etc -xdev -type f -perm -o+w 2>/dev/null
find / -xdev -type d -perm -0002 ! -perm -1000 2>/dev/null
find /usr /opt /usr/local -xdev -type f -perm /6000 2>/dev/null \
  | while read -r f; do rpm -qf "$f" >/dev/null 2>&1 || echo "SUID NOT FROM A PACKAGE: $f"; done
stat -c '%a %U %n' ~ ~/.ssh ~/.gnupg ~/.netrc ~/.pgpass ~/.git-credentials \
  ~/.docker/config.json ~/.aws ~/.config/gh ~/.kube 2>/dev/null
grep -rlE '(api[_-]?key|secret|token|passwo?rd)[[:space:]]*=' \
  ~/.bashrc ~/.bash_profile ~/.profile ~/.config/fish/config.fish 2>/dev/null
```

A SUID binary that no package owns is an R1 candidate — either it is a manually
installed tool, or something that should not be there. Never dismiss it from
the armchair; always report it.

**In the report you write the path and the nature, never the contents.** The
report gets committed, so a token value, key contents or a password must never
end up in it (CLAUDE.md §7). A correct finding reads "`~/.git-credentials`
exists, permissions `0644`" — not what is inside. That is why `grep -rl` (file
names only), never `grep -r`.

### 6. Kernel, LSM and boot

```bash
getenforce 2>/dev/null; aa-status --enabled 2>/dev/null && echo "AppArmor active"
cat /proc/cmdline
sysctl kernel.kptr_restrict kernel.dmesg_restrict kernel.yama.ptrace_scope \
  net.ipv4.ip_forward fs.protected_hardlinks fs.protected_symlinks 2>/dev/null
mokutil --sb-state 2>/dev/null
lsblk -o NAME,FSTYPE,TYPE,SIZE,MOUNTPOINTS
journalctl -b --no-pager -g AVC --since=-7d | tail
```

In `/proc/cmdline` look for `selinux=0`, `enforcing=0`, `apparmor=0`,
`mitigations=off`, `nopti` — each of them switches a protection off permanently
and survives a reboot, so the only way to notice is to look here. It is R2 at
minimum; `selinux=0` on a machine that should be Enforcing according to
`facts.md` is R1, because the whole rest of the audit then rests on a protection
that does not exist.

Missing `crypto_LUKS` in the `lsblk` output is R2 on a laptop (a thief reads
everything) and R3 on a desktop at home — decide from `facts.md` (chassis) and
say what you based the decision on.

Non-default SELinux booleans belong in the root block:
`sudo semanage boolean -l -C` lists only those changed from the default state,
which is exactly the list you want.

### 7. Services and automation

```bash
systemctl list-unit-files --state=enabled --type=service --no-pager
systemctl --user list-unit-files --state=enabled --no-pager
systemctl list-timers --all --no-pager
grep -rlE 'ExecStart=.*(/home/|/tmp/)' /etc/systemd/system ~/.config/systemd/user 2>/dev/null
ls -la /etc/cron.d /etc/cron.daily /etc/cron.hourly 2>/dev/null; crontab -l 2>/dev/null
ls -la ~/.config/autostart/ 2>/dev/null
loginctl show-user "$USER" | grep -i linger
systemd-analyze security --no-pager | head -20
```

A system unit whose `ExecStart` points into home or `/tmp` is a silent path to
privilege escalation: whoever can overwrite that script gains the privileges of
the unit — usually root. It is R1, even though it looks innocent.

`systemd-analyze security` rates almost everything without sandboxing as
*unsafe*. Do not copy its scores into the table — go through only the services
that actually listen on the network according to phase 3.

### 8. Root-only reads — collect and present

During phases 1–7, note down what you could not read without root. **Present it
as one block before building the table**, not at the end and not in passing.
For this skill the root block is especially important: without `sshd -T`,
`firewall-cmd` and `sudoers`, exactly the questions that decide between R1 and
R4 stay unanswered.

**Do not run `sudo` yourself — it has no TTY for the password and fails.** Hand
the user a script that saves the output to a file, then read that file. Write
the block so that it works in their shell (see `facts.md`; fish does not support
`{ …; }` or `for … done` — wrap it in a file and hand over `bash <path>`).

```bash
cat > tmp/sec-audit.sh <<'EOF'
sudo sshd -T 2>/dev/null | grep -E '^(permitrootlogin|passwordauthentication|permitemptypasswords|x11forwarding|allowusers|allowgroups|port|listenaddress|maxauthtries)'
sudo awk -F: '$2==""' /etc/shadow
sudo grep -rh -E 'NOPASSWD|ALL *= *\(ALL' /etc/sudoers /etc/sudoers.d/ 2>/dev/null
sudo ss -tulpn
sudo firewall-cmd --list-all-zones | grep -A12 '(active)'
sudo semanage boolean -l -C 2>/dev/null
sudo nft list chain ip filter DOCKER 2>/dev/null
EOF
bash tmp/sec-audit.sh > tmp/sec-audit.txt 2>&1; echo done
```

`tmp/` is in `.gitignore`. **Delete the file once you have read it** — it
contains the list of open ports, user names and the sshd configuration, which is
exactly what does not belong in the repository.

**After presenting the block, always check whether the output is already on
disk** (`ls -la tmp/`) — the user may have run it before you asked. Writing
"not provided" in the report while the file is sitting right there is worse than
not asking at all.

The `Not checked` section may contain only what the user declined, or what does
not exist on the machine. Never what you did not ask about.

## Risk

A scale of its own, R1–R4, not the P1–P4 of the `system-check` skill — it rates
a different axis. Risk is **impact × reachability**, not how bad the finding
sounds.

| Code | Meaning | When to act |
|---|---|---|
| **R1** | Reachable from somewhere other than this machine, or leads directly to losing control of the account or the data. | Now |
| **R2** | Exploitable by code already running on the machine as the user — browser, package from npm/pip, game, extension. | Within days |
| **R3** | Defense in depth. Does not cause a breach on its own, but makes the damage bigger when something else fails. | When convenient |
| **R4** | Distribution default, an understood and accepted risk, or system design misread as a hole. | Never, just record it |

The two things that most often shift the level:

- **The address.** Loopback versus `0.0.0.0` is the difference between R4 and
  R1 for exactly the same service.
- **Who else has an account on the machine.** Most "local escalations" are R4
  on a single-user desktop. On a shared machine the very same findings jump
  to R2.

## Output

Always a table, sorted from the highest risk. Summarize R4 in one final row.

```markdown
| # | Risk | Finding | Who and from where | Proposed fix |
|---|------|---------|--------------------|--------------|
| 1 | R1 | Container `pg` publishes 5432 on `0.0.0.0`, firewalld does not know about it | Anyone on the LAN; docker bypasses the zones with its own nft chain | Republish on `127.0.0.1:5432` |
| 4 | R4 | `user` in `wheel`, `docker`, `libvirt`; home `0755`; avahi and cups running | Nobody extra — single-user desktop | Record in NOTES.md as an accepted risk |
```

Below the table:

1. **What is clean** — one sentence on what you verified and found in order.
   "Nothing found" is also a result, and the user needs to know you looked.
2. **What you did not check** — root access that was not approved, or places
   you could not see into.
3. **Accepted risks** that you found in `NOTES.md` and therefore do not report.
4. **Proposed fix order** — where to start, not a list of everything.
5. **An offer of a report**, in one sentence at the end.

### Report

**At the end of the audit, offer to generate a report** — in one sentence. Do
not write it by hand; build the JSON and run the generator:

```bash
python3 .claude/skills/security-audit/audit.py findings.json
```

Without `-o` it derives the path itself:
`hosts/<hostname>/reports/<YYYY-MM-DD_HHMM>-security.md`. The timestamp is
mandatory — audits are compared between runs, so they must never overwrite
each other.

The report language is taken from `language` in `hosts/sysadmin.toml` (`"en"`
or `"cs"`; a missing file or key means `en`), and `--lang en|cs` overrides it.
The generator localizes the headings, labels and the risk legend; write the
free-text values in the JSON in the same language. The JSON keys and the codes
`R1`–`R4` are the same in every language.

The required keys of a finding are `sev`, `title`, `attacker`, `fix`; fill in
`evidence` whenever there is any.

```json
{
  "hostname": "host-1",
  "timestamp": "2026-08-31 14:20",
  "distro": "Fedora Linux 44 (KDE Plasma)",
  "kernel": "7.1.10-200.fc44.x86_64",
  "threat_model": "Single-user desktop behind NAT; the boundary is the account user versus the internet, not user versus root.",
  "findings": [
    {"sev": "R1", "area": "containers",
     "title": "Short name of the finding",
     "detail": "What exactly is configured.",
     "evidence": "The command and what it showed — never the value of a secret.",
     "attacker": "Who would exploit it, and from where they can reach it.",
     "impact": "What it means for the user.",
     "fix": "One sentence on what to do about it."}
  ],
  "clean": ["What was verified and found in order"],
  "accepted": ["A risk from NOTES.md, which is therefore not reported"],
  "not_checked": ["What you did not check, and why"],
  "next_steps": ["Proposed fix order"]
}
```

The generator sorts the findings by risk and computes the summary counts
itself — do not pre-sort them. Save the JSON to the scratchpad, not to the
repository, and **check it for secrets before running the generator**: a token
value, key contents, a password from a config file or the machine's public IP
address do not belong in a committed report.

Fixes that come out of the audit are recorded in a separate
`<TS>-intervention.md` by the `intervention.py` generator of the `system-check`
skill — the audit and the intervention log are kept apart, just as with the
system check.

## After the audit

**Everything that applies only to this machine belongs in `hosts/<hostname>/`.**

- **An accepted risk**: add it to `NOTES.md` under the **Accepted risks**
  section (headings in host files use the language from `hosts/sysadmin.toml`),
  as one line: date, what, why it is accepted, when to reconsider it. Without
  that, the next run reports it as a finding again and the user has to decide
  all over again.
- **An R1/R2 finding that was not fixed**: record it with the date — the next
  run will recognize that it is still there.
- **Compare with the previous audit**: `ls hosts/$(hostname)/reports/*-security.md`
  and `git diff --no-index` between them (`hosts/` is a separate repository,
  ignored by this one). A new open port compared with the previous run is a
  finding in itself, even if the service looks harmless.

## Common mistakes

| Mistake | Why it is wrong |
|---|---|
| Reporting a general recommendation without evidence from the machine | "Disable root login" on a machine where sshd is not even running is noise that casts doubt on the rest of the table. |
| Reporting the distribution default as a hole | §6. Verify with `rpm -V`, or confirm that no custom config file exists. |
| Rating severity by how bad it sounds | Risk is impact × reachability. An open port on loopback is not an open port. |
| Passing off a local escalation on a single-user desktop as R1 | `user` in `wheel` is system design. This is the most common false alarm of the whole audit. |
| Forgetting that Docker bypasses firewalld | An empty `firewall-cmd --list-ports` above a published container looks like a clean result, and it is not. |
| Reading the sshd configuration from the file | Only `sshd -T` gives the effective value. Drop-ins and crypto-policies change it. |
| Copying key, token or password contents into the report | The report gets committed. §7. The report gets the path and the permissions, not the value. |
| Running `nmap` or another scanner | An active intervention on the network. `ss` and `firewall-cmd` tell you the exposure more precisely and without risk. |
| Fixing it on the spot, "it's just one `chmod`" | The audit is read-only. A change is a new task that needs approval under §3a. |
| Writing "requires root" instead of asking | The request is one line. Without the root block, half of the audit is unanswered. |
| Declaring the root output not provided without `ls tmp/` | The user may have run it before you asked. |
| Leaving `tmp/sec-audit.txt` lying around | It is a list of open ports and accounts. Delete it after reading. |
| Copying `systemd-analyze security` scores into the table | It marks almost everything as unsafe. Without correlating with phase 3 it is not a finding. |
| Not comparing with the previous audit | A change since the previous run is often the only real finding. |
| Declaring a port new just because it was not in `ss` in the previous run | Socket- and D-Bus-activated daemons start on demand. Check the package install date and the unit start time. |
| Taking `flatpak remote-ls --updates` as a finding | It compares against a stale cache. Verify with `flatpak update --no-deploy`. |
