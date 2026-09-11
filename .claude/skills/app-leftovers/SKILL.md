---
name: app-leftovers
description: Use when the user asks to find leftovers from uninstalled software - "orphaned config", "leftover files", "what is left after uninstalled programs", "orphaned files", "app leftovers", "unused packages" - or asks what is taking up space in /etc and the home directory. Also use before migrating the machine or after removing a larger stack of software.
---

# Application leftovers

A search for files, packages, accounts and objects left behind by software that
is no longer on the machine. The output is **a table of candidates sorted by
confidence** — not a list of everything that is large.

**Core principle:** *Absence of evidence is not proof of an orphan.* The package
manager knows what it installed, but it knows nothing about pip, cargo,
AppImages and manually unpacked archives. A directory for which you cannot find
a package is therefore **not** an orphan — it is a directory for which you did
not find a package. The difference between those two is this whole skill.

The skill **never deletes anything.** Deletion is a separate task under
CLAUDE.md §3a.

## Rules of engagement

| What | How |
|---|---|
| Read-only command without root | I run it straight away, without asking. |
| Read-only command with root (`rpm -qf` over unreadable parts of `/etc`, `virsh` against the system instance) | I collect them and submit them for approval **as one block**. |
| Anything that deletes or cleans up | Always §3a: what / why / impact / rollback. Never as part of the search. |

### Commands that look like reading but change state

This is the main trap in cleanup — "purging" tools have no dry run:

| Do not run | Why | Read-only replacement |
|---|---|---|
| `docker system prune`, `docker image prune` | **Has no `--dry-run`.** Deletes immediately. | `docker images -f dangling=true`, `docker volume ls -f dangling=true` |
| `podman system prune` | Same. | `podman images --filter dangling=true` |
| `flatpak uninstall --unused` | It asks, but it is an uninstall. | `flatpak list --app --columns=application,runtime` against `flatpak list --runtime` |
| `dnf autoremove` | Removes. | **`dnf autoremove --assumeno`** — prints the whole transaction including the space freed and exits without changing anything. Better than `dnf repoquery --unneeded`, because it also shows what the solver pulls in on top. |
| `journalctl --vacuum-*`, `dnf clean all` | They delete. | `journalctl --disk-usage`, `du -sh /var/cache/*` |

## Procedure

### 0. Machine context

```bash
cat hosts/$(hostname)/facts.md hosts/$(hostname)/NOTES.md 2>/dev/null
```

Without the facts you cannot work out the right package manager. In `NOTES.md`
look for the **Known false alarms** section (headings in host files use the
language from `hosts/sysadmin.toml`): whatever is listed there goes into C4 as a
single line — not back into the findings.

### 1. Inventory — what IS on the machine

**This is the foundation of everything else and must not be skipped.** Every
orphan is a claim that "this belongs to nothing", and that claim is only as good
as the list it was checked against. An incomplete inventory does not produce
fewer findings — it produces false ones.

```bash
rpm -qa --qf '%{NAME}\n' | sort -u          # deb: dpkg-query -W -f='${Package}\n'
flatpak list --app --columns=application,runtime
flatpak list --runtime --columns=application
compgen -c | sort -u                        # everything executable in $PATH
ls -1 /opt /usr/local/bin ~/.local/bin 2>/dev/null
pipx list 2>/dev/null; pip list --user 2>/dev/null
cargo install --list 2>/dev/null; npm ls -g --depth=0 2>/dev/null
find ~ -maxdepth 3 -iname '*.AppImage' 2>/dev/null
ls -1d ~/.local/share/Steam ~/.mozilla ~/.thunderbird 2>/dev/null
```

Note which of these are missing on the machine — **in the report they belong
under "Not searched".** The user must know which layer of installations was not
included in the comparison.

**Also look for disks that are not mounted:**

```bash
lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINTS
findmnt -rno TARGET,SOURCE | grep -v '^/\(proc\|sys\|dev\|run\)'
```

A partition without `MOUNTPOINTS` is invisible to `find`. The claim "there is
nothing like that on the disks" made over an unmounted disk is false — the
correct answer is *not searched*. On a real machine two disks with complete
system installations were left out this way, and one of them
held the VMs that had come up a few findings earlier. Mounting it is a change
under §3a: propose it, do not do it.

### 2. Package layer

```bash
dnf autoremove --assumeno                   # what would go, including space freed
dnf repoquery --unneeded                    # nothing depends on them
dnf repoquery --extras                      # installed, but no longer in any repo
dnf history list --reverse | head -40       # when what was removed
find /etc \( -name '*.rpmsave' -o -name '*.rpmnew' -o -name '*.rpmorig' \) 2>/dev/null
ls -1 /etc/yum.repos.d/
```

The parentheses in `find` are mandatory — without them `-o` binds differently
and `2>/dev/null` filters only part of the output. Check the count, not just
that the command finished.

**Do not replace `autoremove` with your own curation until you have evidence
for it.** Your own list of "what to remove and what to keep" looks responsible,
but it is only a guess against a solver that, unlike you, knows the whole
dependency graph. The only objection that holds up against it is specific and
verifiable: *this package is used by software outside the package manager that
dnf does not know about.* Verify it, do not just state it:

```bash
for b in /usr/local/bin/* ~/.cargo/bin/* ~/.local/bin/*; do
  ldd "$b" 2>/dev/null | grep -q '<library name>' && echo "$b"
done
```

If that comes back empty, the curation has nothing to stand on and the
distribution tool wins (CLAUDE.md: the distribution's recommended practice takes
precedence). On a real run the manual curation did worse than `autoremove` for
21 of 23 packages, and for one of them it was plain wrong. AppImages cannot be
checked this way — they are compressed; but they bundle their libraries, so the
risk is small. That belongs in the report as a limitation, not as a reason to
do nothing.

**Read conditional dependencies in full.** `rpm -q --requires ibus` printed
`ibus-xinit if (cinnamon or deepin-desktop or i3 or …)`. On KDE that condition
is not met, so the dependency does not apply — but `rpm --whatrequires` shows it
as if it did. The `if (…)` line is part of the answer, not decoration.

Tell them apart: **`.rpmsave` = your modification, which the package rescued
when it was removed** (C1 as an orphan, but read it before you delete it — it may
be the only copy of your configuration). **`.rpmnew` = a new default version that
the upgrade did not write over your modification** — that is not an orphan but
an unresolved difference. Report it separately.

Files in `/etc` that no package owns:

```bash
find /etc -type f -print0 2>/dev/null | xargs -0 -n200 rpm -qf 2>&1 \
  | grep -F 'not owned' | awk '{print $(2)}' | sort
```

A large part of the output is **legitimate** files: generated ones
(`/etc/passwd-`, `/etc/*.cache`), your own modifications, things from
`systemd-firstboot`. Of those, only a file whose name matches software removed
according to `dnf history` is an orphan. The rest is C3, not a finding.

### 3. systemd and the desktop

```bash
systemctl list-units --all --state=not-found --no-pager
systemctl --user list-units --all --state=not-found --no-pager
find /etc/systemd ~/.config/systemd -xtype l 2>/dev/null
systemctl list-unit-files --state=masked --no-pager
```

`-xtype l` finds a symlink whose target does not exist — a typical remnant of
`systemctl enable` for a service that a package later took away. **Search only
`/etc/systemd` and `~/.config/systemd`, never `/run/systemd`.** The runtime
directory is full of `units/invocation:*` links that systemd manages internally
and that look broken to `-xtype l` — on a live machine there are over a hundred
of them and they would bury the report. A broken symlink only matters where an
administrator wrote it.

The list of `not-found` units tends to be long and **mostly they are not
orphans**: they are names referenced by someone else's `Wants=`/`After=`
(`apparmor.service`, `iptables.service` on Fedora, `gnome-session.service` in a
KDE session). Of those, only a unit pointed to by a symlink in
`/etc/systemd/system/*.wants/` is a finding.

Dead menu and autostart entries:

```bash
for f in ~/.local/share/applications/*.desktop ~/.config/autostart/*.desktop; do
  [ -e "$f" ] || continue
  line=$(grep -m1 '^Exec=' "$f"); line=${line#Exec=}
  case "$line" in
    \"*) b=${line#\"}; b=${b%%\"*} ;;
    \'*) b=${line#\'}; b=${b%%\'*} ;;
    *)   b=${line%% *} ;;
  esac
  [ -n "$b" ] && ! command -v "$b" >/dev/null 2>&1 && echo "dead: ${f##*/} -> $b"
done
```

**Parsing `Exec=` must handle quotes, otherwise it produces false findings.** A
naive `sed 's/ .*//'` cuts a path containing a space at the first space, you get
a non-existent prefix and report a working entry as dead. On the test machine
this produced exactly one false finding out of six. The `case` above handles
`"`, `'` and the unquoted form.

Only `~`, not `/usr/share/applications` — files there are owned by packages and
the package manager deals with them.

### 4. Home directory

Sizes first, matching only after that — without sizes you do not know what is
worth investigating:

```bash
du -sk ~/.config/* ~/.local/share/* ~/.cache/* ~/.var/app/* 2>/dev/null | sort -rn | head -40
find ~ -maxdepth 4 -name .cache -prune -o -xtype l -print 2>/dev/null \
  | grep -vE '/(Singleton(Lock|Socket|Cookie)|lock|\.lock)$|-runtime$'
```

**A broken symlink in the home directory is usually a live runtime lock, not an
orphan.** Chromium and Electron keep `SingletonLock`/`SingletonSocket`/`SingletonCookie`
pointing to `pid@hostname`, Firefox keeps `lock`, PulseAudio a link into `/run` —
all of them are "broken" even while the application runs. Without the filter
above they make up most of the output. The same goes for `~/.claude/debug/latest`
and similar rotating links: the target changes, and emptiness between rotations
is the normal state.

**Flatpak is the only part of the home directory with hard evidence.** The
directory `~/.var/app/<app-id>` belongs 1:1 to an application; when that
application is not in `flatpak list`, it is C1:

```bash
comm -23 <(ls -1 ~/.var/app 2>/dev/null | LC_ALL=C sort) \
         <(flatpak list --app --columns=application | LC_ALL=C sort)
```

`LC_ALL=C` on **both** sides is mandatory — `comm` compares lines positionally
and with different sort orders it silently produces nonsense instead of an
error.

For `~/.config` and `~/.local/share` there is no evidence. Procedure: match the
directory name against the inventory from step 1, and when it does not match,
add the date of the last write (`stat -c '%y %n'`). **The result is C3, not C1**
— even if it has not been used for three years.

**Substring matching produces nonsense — always read the finding.** Searching
for the pattern `rofi` found `powermanagementprofilesrc`, a KDE configuration
that has nothing to do with `rofi`. A short pattern (`vim`, `code`, `go`, `rofi`)
hits the middle of an unrelated name. Either anchor on the whole directory name,
or go through every hit by eye — in both cases before you write it into the
report.
Move it up to C2 only when `dnf history` proves that the corresponding package
was actually removed.

**`~/.icons` is not checked at all.** The administrator stores icons there by
hand and assigns them independently of menu entries, so a missing reference from
a `.desktop` file proves nothing. "Orphaned icon" is not a finding category —
neither in C3 nor in C4.

`~/.cache` is a separate category: it is a *cache*, not configuration. Report the
space it takes, but as "it will come back", not as an orphan.

### 5. Users and groups

```bash
getent passwd | awk -F: '$(3)>=100 && $(3)<1000 {print $(1), $(3), $(6), $(7)}'
id
for g in $(id -Gn); do getent group "$g" >/dev/null || echo "missing: $g"; done
```

A system account left by a removed package (typically by a service the package
manager created and left alone on removal) is a finding — but **it owns files on
disk.** Before anyone deletes it, find out what it left behind:
`find / -xdev -nouser -o -nogroup` (root, in the batch). Otherwise you end up
with files without an owner, which is a worse state than the original one.

A user's membership in a group left by uninstalled software (`vboxusers` without
VirtualBox) is C2 and purely cosmetic — report it, but not as a priority.

### 6. Containers and virtualisation

```bash
docker images -f dangling=true; docker volume ls -f dangling=true; docker ps -a
podman images --filter dangling=true 2>/dev/null; podman ps -a 2>/dev/null
virsh --connect qemu:///session list --all 2>/dev/null
virsh --connect qemu:///system list --all; virsh pool-list --all
```

The system instance of `libvirt` usually wants root — it belongs in the block
from step 7. `dangling` images tend to be the fattest item in the whole report;
at the same time this is the category where the user most often knows the
reason they are there. Ask, do not delete.

### 7. Root-only reads — collect and submit

During steps 1–6 note down what you could not read without root, and **submit
it as one block** before building the table.

**Do not run `sudo` yourself — it has no TTY for the password and fails.** Hand
the user a block to paste into their terminal that saves the output to a file:

```bash
mkdir -p tmp && { sudo find / -xdev \( -nouser -o -nogroup \) 2>/dev/null; \
  sudo virsh pool-list --all; } > tmp/leftovers-root.txt 2>&1; echo done
```

**Do not assume the user is sitting in bash.** The login shell from
`getent passwd` says little — interactively they may be running fish or zsh,
which do not understand `{ …; }`, `for … done` or heredocs. When the block
contains more than a plain sequence of commands, **do not detect the shell, go
around it**: write a script into `tmp/` inside the repository and hand over the
one-liner `bash ~/path/tmp/root-diag.sh`. Bash is present on the machine even if
the user does not work in it.

`tmp/` is in `.gitignore`. Delete the file after reading it.

**Before you write "not provided", run `ls -la tmp/`.** The user may have run it
before you asked. The "Not searched" section may contain only what the user
declined, or what is not on the machine — never what you did not ask about.

## Confidence instead of severity

For orphans the question is not how much it hurts, but whether it is an orphan
at all.

| Tier | Meaning | When you may assign it |
|---|---|---|
| **C1** | **Confirmed.** The evidence says so directly. | `~/.var/app/X` without flatpak X; dangling symlink; `not-found` unit; `.rpmsave` left by a package whose removal `dnf history` confirms |
| **C2** | **Probable.** Strong indication, evidence missing. | Directory name matches a package that `dnf history` recorded as removed; group left by uninstalled software |
| **C3** | **Candidate.** Only a heuristic — name, age, size. | A directory for which you found no software. The user decides, not you. |
| **C4** | **False alarm.** Checked, belongs to something live. | Into `NOTES.md`, so it does not pop up next time. |

A Czech-language report renders these tiers as `J1`–`J4`; the meaning is the
same.

**Never move an item up because it is large.** 40 GB in C3 is still C3. Size is
a separate column precisely so that it does not push on confidence.

## Output

A table by confidence tier, sorted by size within each tier. Below it:

1. **Inventory** — what was compared against. Without it the reader cannot judge
   how far to trust C3.
2. **Verified, not an orphan** — what you checked and found to be live.
3. **Not searched** — where you could not see and why.
4. **Proposed cleanup order** — what to start with; always C1 first.
5. **An offer of the report** in one closing sentence.

Do not write the report by hand — build the JSON and run the generator:

```bash
python3 .claude/skills/app-leftovers/leftovers.py findings.json
```

Without `-o` it derives the path itself:
`hosts/<hostname>/reports/<YYYY-MM-DD_HHMM>-leftovers.md`.

The report language comes from `language` in `hosts/sysadmin.toml` (`en` or
`cs`; default `en`); `--lang en|cs` overrides it.

```json
{
  "hostname": "host-1",
  "timestamp": "2026-08-29 22:10",
  "distro": "Fedora Linux 44 (KDE Plasma)",
  "inventory": ["2431 RPM packages", "12 flatpaks", "pipx: 3", "cargo: not installed"],
  "items": [
    {"confidence": "C1", "area": "flatpak", "path": "~/.var/app/org.foo.Bar",
     "kb": 421337, "last_used": "2025-03-11",
     "evidence": "flatpak list does not know the application org.foo.Bar",
     "verdict": "delete after reviewing the contents",
     "detail": "Optional paragraph, when one sentence in the table is not enough."}
  ],
  "clean": ["What was checked and is live"],
  "not_checked": ["Where you could not see and why"],
  "next_steps": ["Proposed cleanup order"]
}
```

Keys per item: `confidence`, `area`, `path`, `kb`, `last_used`, `evidence`,
`verdict`, optional `detail`. Top level: `hostname`, `timestamp` (or `date`),
optional `distro` and `kernel`, `inventory`, `items`, `clean`, `not_checked`,
`next_steps`. **The JSON always uses `C1`–`C4`, whatever the report language**;
the generator renders them as `J1`–`J4` in a Czech report. `J1`–`J4` in the JSON
are accepted as aliases; any other or missing value is counted as C3.

`kb` is **kilobytes straight from `du -sk`** — do not write "412 MB" by hand, the
generator formats and adds it up itself. It sums only C1 and C2: C3 is a
hypothesis, and adding it into one number would turn an estimate into a promise.
Save the JSON to the scratchpad, not to the repository.

A deletion is then recorded in the existing `*-intervention.md`
(`.claude/skills/system-check/intervention.py`) — there is no separate record
type for cleanup.

## After the search

- Add a C4 item to `hosts/<hostname>/NOTES.md` under **Known false alarms**
  (in the hosts language from `hosts/sysadmin.toml`), together with the reason
  it is not an orphan. Without the reason the next run will find it again.
- Anything specific to this machine belongs in `hosts/<hostname>/`, not in the
  skill — anywhere else it would lie on the next computer.

## Common mistakes

| Mistake | Why it is wrong |
|---|---|
| Skipping the inventory and matching `~/.config` straight away | Everything installed outside the package manager then looks like an orphan. A false positive that the user deletes is worse than no report. |
| Assigning C1 based on a directory name | C1 means confirmed by evidence. A name is not evidence. |
| Promoting a finding because it is large | Size is a motivation to clean up, not proof of orphanhood. There are two columns by design, not by accident. |
| Running `prune` "just to try" | It has no dry run. It is a change under §3a, and an irreversible one. (`dnf autoremove --assumeno`, on the other hand, does have a dry run — use it.) |
| Replacing `autoremove` with your own curation without evidence | The solver knows the whole dependency graph, you do not. Curation needs a specific, verified objection, not caution. |
| Reading `rpm --whatrequires` without the conditions | It shows a conditional `if (…)` dependency even when the condition is not met. It looks like "requires", yet it does not. |
| Looking for broken symlinks in `/run/systemd` | They are always there, over a hundred of them. The runtime directory is not a place where the administrator writes. |
| Reporting "orphaned icons" in `~/.icons` | Icons are assigned by hand, outside `.desktop` files. A made-up check that produces only false findings. |
| Reporting `SingletonLock` or `lock` as an orphan | It is a live lock of a running application. "Broken" is its normal state. |
| Parsing `Exec=` without handling quotes | A path with a space gets cut and a working entry is reported as dead. |
| `comm` without `LC_ALL=C` on both sides | With different sort orders it does not return an error, it returns nonsense. |
| Deleting `.rpmsave` without reading it | It is the last copy of your own configuration, rescued by the package on removal. |
| Reporting `.rpmnew` as an orphan | It is not a leftover, it is an unresolved difference against a new default version. It belongs to another category. |
| Proposing to delete a system account without the `-nouser` check | Files without an owner appear. A worse state than the original. |
| Counting `~/.cache` into reclaimable space | It comes back. It is a cache, not an orphan. |
| Handing over a root block in bash syntax without checking the shell | fish understands neither `{ }`, `for … done` nor heredocs. A block more complex than a sequence of commands belongs in a script run through `bash`. |
| Declaring "it is not on the disks" without `lsblk` | `find` does not see an unmounted partition. The answer is not searched, not not found. |
| Trusting substring matching | The pattern `rofi` hits `powermanagementprofilesrc`. A short pattern is coincidence, not a finding. |
| Reporting "not provided" without `ls tmp/` | The user may have run it before you asked. |
| Writing the report by hand | That is what `leftovers.py` is for. Writing by hand means runs that cannot be compared. |
| Cleaning up straight away | The skill is read-only. Deletion is a new task with approval. |
