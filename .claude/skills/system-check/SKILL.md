---
name: system-check
description: Use when the user asks to check system logs or system health - "check the logs", "is something wrong", "look over the system", "what is in the journal", "check system logs", "system health check" - or when starting work on a machine whose state is unknown. Also use before and after a larger intervention (upgrade, driver swap, service change) to compare state.
---

# System check

A repeatable read-only inspection of a running Linux system: failed services,
journal errors, process crashes, disk health, capacity, security messages. The
output is **a table of findings with severity and a proposed fix** — not a log
dump.

**Core principle:** a raw log is worthless, because a handful of patterns repeat
in it thousands of times. Value only appears in a *deduplicated* list of
patterns sorted by frequency.

## Rules of engagement

| What | How |
|---|---|
| Read-only command without root | Run it straight away, without asking. |
| Read-only command with root (`smartctl`, `ausearch`, `dmidecode`) | Collect them and present them for approval **as one line each**, typically in a single batch after the basic round. |
| Any change to the system or to user files | Always per CLAUDE.md §3a: what / why / impact / rollback. Never as part of the check. |

The check itself **never fixes anything.** A fix is a separate task that the
user asks for after reading the table.

## Procedure

### 0. Machine context

```bash
cat hosts/$(hostname)/facts.md hosts/$(hostname)/NOTES.md 2>/dev/null
```

On a machine managed over SSH (listed under `[remote]` in `hosts/sysadmin.toml`),
use its hostname instead of `$(hostname)` and run every command in this skill
through `ssh -a -o BatchMode=yes <alias>`. Root reads use the two-line handoff
from CLAUDE.md §4.

If there are no facts, agree on collecting them (CLAUDE.md §4) — without them
you cannot derive the right commands. In `NOTES.md` look for the **Known noise**
section (headings in host files use the language from `hosts/sysadmin.toml`):
whatever is listed there goes into the report as P4 in one summary row, not as
separate rows.

### 1. Overall state

```bash
systemctl is-system-running; uptime
systemctl --failed --no-pager
systemctl --user --failed --no-pager
journalctl --list-boots | tail -5
```

### 2. Journal errors — deduplicated

This is the core. Without `uniq -c` there is no making sense of it.

```bash
journalctl -p 3 -b --no-pager -o short-iso \
  | grep -vE '#[0-9]+ +0x|Stack trace of thread|^\s*$|ELF object binary|Module .* from rpm|without build-id' \
  | sed -E 's/^[^ ]+ [^ ]+ //; s/\[[0-9]+\]//; s/:[0-9]+ /:N /g; s/[0-9]{3,}/N/g' \
  | sort | uniq -c | sort -rn | head -40
journalctl -p 3 -b --no-pager | wc -l
```

Every link of the chain is there for a reason — do not shorten it:

- `grep -vE` throws away the **entire** coredump backtrace (frames, thread
  headers, module list). Without it the backtraces drown out everything else
  and the real errors get lost under hundreds of `Module libX from rpm …` lines.
- `s/:[0-9]+ /:N /g` merges line-number references (`rules.d/x.rules:97`);
  otherwise one broken file looks like a hundred different errors.
- `s/[0-9]{3,}/N/g` merges variants that differ only in PID or port.

On a real machine this chain reduced 947 lines to 12 patterns, and only then
did a one-off firewalld error become visible, hidden until then by 220
repetitions of a udev message. **Check the ratio** of `wc -l` **to the number of
patterns** — when it is below 3:1, the dedup did not work and your `sed` is
wrong.

Do the same for warnings (`-p 4..4`) and for the previous boot (`-b -1`) if the
current one has only been running briefly. For a longer-term picture add
`--since=-7d`.

### 3. Process crashes

```bash
coredumpctl list --since=-14d --no-pager
du -sh /var/lib/systemd/coredump
```

For a repeated crash, extract the cause: `coredumpctl info <PID> | head -40`.
If the crash repeats on every boot, it is a configuration problem, not chance.

### 4. Hardware and kernel

```bash
journalctl -k -b -p 4 --no-pager -o cat | sed -E 's/[0-9]{2,}/N/g' | sort | uniq -c | sort -rn | head -30
journalctl --since=-30d --no-pager -g "Out of memory|oom-kill" | tail
journalctl --since=-30d -k --no-pager -g "I/O error|ata[0-9]|nvme|medium error|reset" | tail -20
journalctl -b -k --no-pager -g "btrfs|EXT4-fs error|XFS" | grep -iE "error|corrupt|csum" | tail
lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS
```

For a disk finding, always try to **correlate the time of the error with the
time of a timer** (`systemctl list-timers --all`) — `fstrim` on a spinning disk
or `raid-check` can produce ATA errors that look like a dying disk. Report a
correlation as a correlation, not as the cause.

### 5. Firmware — is the BIOS up to date

**Always do this phase.** It is read-only, needs no root and no network, and
takes a few seconds. Firmware is the only layer of the machine that
distribution updates never fix and that silently ages for years — and yet it
explains whole classes of errors (amdgpu/PSP, ACPI, C-states, suspend, USB4)
that look like a driver problem in the log.

```bash
cat /sys/class/dmi/id/{sys_vendor,product_name,board_name,bios_vendor,bios_version,bios_date} 2>/dev/null
fwupdmgr get-upgrades 2>&1 | tail -30
fwupdmgr get-devices --no-unreported-check 2>/dev/null | grep -A6 -E "System Firmware|UEFI dbx"
grep -m1 microcode /proc/cpuinfo; journalctl -k -b --no-pager -g microcode | tail -3
```

If there is no `fwupdmgr`, stick with DMI — the finding then reads "firmware
age X, not verified with the vendor", not "firmware is up to date".

#### Three pitfalls that turn this step into a falsely reassuring routine

1. **Silence from `fwupd` is not proof of being up to date.** "No updates
   available" only means that LVFS has nothing newer *for this GUID*.
   Motherboard vendors (MSI, ASUS, Gigabyte) mostly do not publish there at
   all. Tell the two cases apart explicitly:

   ```bash
   fwupdmgr get-releases <device-id-System-Firmware>
   ```

   `No releases found` = **the vendor does not ship to LVFS**, no check took
   place. A list of versions = the check took place and the firmware really is
   the newest. The difference between "verified, it is current" and "could not
   be verified" belongs in the report; the first is a line in *What is clean*,
   the second in *What you did not check*.

2. **The `System Firmware` version is not the BIOS version.** `fwupd` shows the
   number from ESRT (e.g. `401`), the vendor talks about `1.A92`. In the facts
   and the report always write `bios_version` + `bios_date` from DMI, ESRT at
   most as a supplement.

3. **Age alone is not a finding.** A two-year-old stable firmware on a machine
   without symptoms is fine. It becomes a finding only when a second thing
   joins the age: an offered update, security content, or a specific symptom
   from phases 2–4 that the firmware explains.

#### When it is a finding and how serious

| Situation | Severity |
|---|---|
| `fwupd` offers a **UEFI dbx** update | **P2** — an outdated revocation list undermines Secure Boot |
| `fwupd` offers a system firmware update with security content | **P2** |
| `fwupd` offers an update without security content | **P3** |
| Old firmware **+ a symptom in the log** that a newer version fixes according to the changelog | **P3**, `fix` says "verify with the vendor", not "flash it" |
| Old firmware, no symptom, vendor does not publish to LVFS | **P4** as one row, or just a sentence in *What is clean* |
| Firmware matches the latest released version | Not a finding — belongs in *What is clean* |

Never propose a flash just because a newer version exists. **A BIOS flash is
one of the few irreversible operations on the machine**: it resets settings,
renumbers UEFI boot entries and bricks the board if interrupted. To be worth it,
it must have documented content — an AGESA security patch, a changelog entry
matching a real symptom — not merely a higher number.

#### What needs approval

Reading DMI and querying the local `fwupd` cache are §3b — no asking. On the
other hand, **these fall under §3a**: `fwupdmgr refresh` (downloads metadata,
outgoing network), `fwupdmgr update`, any flash, and likewise **opening the
vendor's website to look up the latest version** — that is outgoing network
too. So ask for verification with the vendor in one line, and only when a
symptom or an offered update justifies it.

The output of `fwupdmgr get-devices` contains **serial numbers** of peripherals.
Do not copy it whole into the report or into the repository (CLAUDE.md §8b) —
the finding gets the version and date, not the dump.

#### Recording in the facts

Keep the detected version in `hosts/<hostname>/facts.md` on the `Firmware` line
in the form `<version> (<date>)`. When it differs from the recorded one, the
firmware has been flashed since last time — update the facts and look in
`NOTES.md` for a record of that intervention. A difference between the recorded
and the actual version is a finding in itself: either someone flashed without a
record, or the firmware was rolled back after a board replacement.

### 6. Capacity

```bash
df -hT -x tmpfs -x devtmpfs
journalctl --disk-usage
ls -1 /boot/vmlinuz-* ; grep -h installonly /etc/dnf/dnf.conf 2>/dev/null
free -h
```

Report `/boot` above 70 % — the next kernel update may get stuck on it.

### 7. Security and configuration

```bash
getenforce 2>/dev/null; journalctl -b --no-pager -g AVC --since=-7d | tail
for f in /etc/udev/rules.d/*.rules; do head -c 200 "$f" | grep -qE '^(#|[A-Z]|$)' || echo "SUSPICIOUS: $f"; done
grep -ho 'GROUP="[^"]*"' /etc/udev/rules.d/*.rules 2>/dev/null | sort -u \
  | sed 's/GROUP="//;s/"//' | while read g; do getent group "$g" >/dev/null || echo "missing group: $g"; done
systemctl list-timers --all --no-pager
```

Hand-written or downloaded rules in `/etc/udev/rules.d/` are a recurring source
of silent errors: downloaded files tend to be HTML error pages, and the groups
they reference do not exist on the given distro.

### 8. Root-only reads — collect and present

During phases 1–7, note down what you could not read without root. **Present it
as one block before building the table** — not at the end, not in passing.

```bash
sudo smartctl -a /dev/sdX        # disk health, when there are ATA/NVMe errors
sudo ausearch -m avc -ts today   # SELinux denials straight from audit.log
sudo dmidecode -t memory         # RAM, when hardware is suspected
```

The format is one line per command per CLAUDE.md §3b: what I will run and why I
need to know it. In a batch, not one by one.

**Do not run `sudo` yourself — it has no TTY for the password and fails.** The
user's consent is not the same as the ability to execute the command. So hand
them a ready block to paste into their terminal that saves the output to a
file, and then read that file:

```bash
mkdir -p tmp && { sudo smartctl -a /dev/sda; sudo smartctl -a /dev/sdb; \
  sudo ausearch -m avc -ts today; } > tmp/root-diag.txt 2>&1; echo done
```

`tmp/` is in `.gitignore`, so the output does not end up in a commit. Delete the
file after reading it — it may contain serial numbers and system paths.

**After presenting the block, always check whether the output is already on
disk.** Before saying "waiting for the user", run `ls -la tmp/` and read the
file — the user may have run it before you asked, or in another window.
Writing "not provided" in the report over a file that is sitting there is worse
than not asking at all: it looks like a closed finding while it is really just
unread output. Check again right before building the report.

**The `Not checked` section of the report may only contain what the user
declined, or what does not exist on the machine.** Never what you did not ask
about. A note saying "requires root" instead of an actual question looks like
following the rule, but it leaves a finding open — and it tends to be exactly
the one that decides between P3 and P1.

The trigger you must not miss: **any finding whose `fix` starts with the word
verify, where that verification needs root.** Such a finding cannot be closed
without asking.

## Severity

| Code | Meaning | When to act |
|---|---|---|
| **P1** | Risk of data loss, unavailability, or a security breach. | Now |
| **P2** | Something is genuinely broken or measurably getting worse. | Days |
| **P3** | Works, but wastes resources, pollutes the log, or will break on the next upgrade. | When convenient |
| **P4** | Understood and harmless noise. | Never |

Assign by **impact on the user**, not by how loud it is in the log. 750 lines
about a missing group are P3. A single line about a csum error on btrfs is P1.

## Output

Always a table, sorted from the most serious. Summarise P4 in one final row.

```markdown
| # | Sev. | Finding | Impact | Proposed fix |
|---|------|---------|--------|--------------|
| 1 | P2 | `example.service` crashes on every start in a bundled library | Coredump 1×/boot; the feature it provides silently falls back | Remove the unused bundled libraries the service loads by mistake |
| 4 | P4 | Three harmless driver and desktop-service messages | None | Record in NOTES.md as known noise |
```

Below the table:

1. **What is clean** — one sentence on what you verified and found in order.
   A finding of "nothing" is a result too, and the user needs to know you looked.
2. **What you did not check** — areas requiring root that were not approved,
   or that you could not see into.
3. **Proposed fix order** — where to start, not a list of everything.
4. **Report offer** — one sentence at the very end. See below.

## Two outputs: report and intervention log

A session has two different documents and **they do not mix**:

| File | What it contains | When it is created |
|---|---|---|
| `<TS>-check.md` | What you **found**. Read-only diagnostics, findings, severity, proposals. | When the check is done. |
| `<TS>-intervention.md` | What was **resolved and how**. Interventions carried out, verification, rollback. | Only at the end of the session, after the fixes. |

The report is a snapshot of the state. What you did afterwards does not belong
in it — that is what the intervention log is for. When a session ends without a
single fix, no intervention log is created.

**Both documents are Markdown**, not HTML: they can be read with `cat` and
`less` even on a machine without a desktop, compared with `git diff`, and need
no browser. Do not write them by hand — build the JSON and run the generator.

**Language.** Both generators write in the language set by `language = "en"` or
`"cs"` in `hosts/sysadmin.toml`; a missing file or key means `en`. `--lang en|cs`
overrides the file. The JSON is the same for both languages: keys, severity
codes and `status` values are always English, only the rendered text is
localized.

### Check report

**At the end of every check, offer to generate the report** — in one sentence,
not a long question. The user says yes or no.

```bash
python3 .claude/skills/system-check/report.py findings.json
```

Without `-o` it derives the path itself:
`hosts/<hostname>/reports/<YYYY-MM-DD_HHMM>-check.md`. The timestamp in the name
is mandatory — reports are compared between runs, so they must never be
overwritten.

The JSON has this shape — the keys `sev`, `title`, `impact`, `fix` are required,
the rest is optional:

```json
{
  "hostname": "host-1",
  "timestamp": "2026-08-29 18:03",
  "distro": "Fedora Linux 44 (KDE Plasma)",
  "kernel": "7.1.10-200.fc44.x86_64",
  "uptime": "53 min",
  "findings": [
    {"sev": "P2", "area": "example.service", "title": "Short finding title",
     "detail": "Evidence from the log, frequency, since when.",
     "impact": "What it does to the user.",
     "fix": "One sentence on what to do about it."}
  ],
  "clean": ["What was verified and found in order"],
  "not_checked": ["What you did not check and why"],
  "next_steps": ["Proposed fix order"]
}
```

The generator sorts the findings by severity and computes the summary counts
itself — do not pre-sort them. Save the JSON to the scratchpad, not to the
repository.

### Intervention log

**At the end of a session in which something was fixed**, write down what was
resolved and how:

```bash
python3 .claude/skills/system-check/intervention.py interventions.json
```

Path without `-o`: `hosts/<hostname>/reports/<YYYY-MM-DD_HHMM>-intervention.md`.

```json
{
  "hostname": "host-1",
  "timestamp": "2026-08-29 21:40",
  "report": "2026-08-29_1836-check.md",
  "interventions": [
    {"status": "resolved", "area": "udev",
     "title": "Short intervention title",
     "problem": "Which finding from the report this addresses.",
     "how": "The full command or a description of the change, multiline is fine.",
     "verify": "How you verified it worked — actual output, not an assumption.",
     "rollback": "How to undo it, or that it cannot be undone."}
  ],
  "repo_changes": ["What changed inside the repository"],
  "unresolved": ["A finding that was left unresolved, and why"],
  "next_steps": ["What to do next time"]
}
```

`status` is one of `resolved`, `partial`, `not_done`, `reverted`. The log shows
them in the report language (`not_done` renders as "not done"); any other value
is printed as it is and left out of the summary counts.
The `verify` field is not filled in from memory — it takes the actual output of
a command.

The optional **`note`** field is rendered last, as an indented note. It holds
what turns a list of successes into an honest record: **what you predicted
wrongly, what the user overruled after your objection, and where your original
approach was worse than the one finally used.** Without it the next run repeats
the same mistake and nobody learns that the warning was ever given.

## After the check

**Everything that applies only to this machine belongs in `hosts/<hostname>/`**
— nowhere else. Not in the skill, not in global memory, not in `playbooks/`. The
skill describes the procedure in general; what is peculiar about this particular
machine is remembered by its own directory, because anywhere else it would be a
lie on the next machine.

- Add a new P4 item to `hosts/<hostname>/NOTES.md` under **Known noise**
  (headings in host files use the language from `hosts/sysadmin.toml`), so the
  next run does not report it as a finding again.
- Record a P1/P2 finding in `NOTES.md` with a date, even if it is not fixed
  right away — the next run will tell whether it is getting worse.
- Reports and intervention logs stay in `hosts/<hostname>/reports/`.
- All of it is inside the working copy (`hosts/` is the hosts repository cloned
  into it), so writing it needs no approval.

## Common mistakes

| Mistake | Why it is wrong |
|---|---|
| Dumping raw `journalctl` output on the user | The task is "find the problem", not "show me the log". Without dedup and severity it is not an answer. |
| Reporting noise as a finding | Nine P4 rows bury one P1. Noise belongs in a single summary row. |
| Declaring a correlation to be the cause | "ATA error at the time of fstrim" is a hypothesis. Say it as a hypothesis. |
| Fixing it right away | The check is read-only. A change is a new task with approval per §3a. |
| Writing the report by hand | That is what `report.py` is for. Writing by hand means a different format every time and runs that cannot be compared. |
| Saving a note about the machine anywhere other than `hosts/<hostname>/` | On the next machine it would be a lie. Local facts go to the local directory. |
| Writing "requires root" in the report instead of asking | The question is one line. Not asking means leaving the finding open and pretending it is done. |
| Declaring root output not provided without `ls tmp/` | The user may have run it before you asked. An unverified assumption in the report looks like a finding. |
| Writing interventions carried out into the check report | The report is a snapshot of findings. Interventions belong in a separate `*-intervention.md` at the end of the session. |
| Finishing a fix without an intervention log | The next run cannot tell whether the finding disappeared by itself or someone fixed it. |
| Declaring firmware up to date based on "No updates available" | Most motherboard vendors do not publish to LVFS. Silence from `fwupd` means "could not be verified", not "it is the newest". |
| Proposing a BIOS flash just because of a higher version number | An irreversible operation that resets settings and can brick the board. Without documented content it is not worth it. |
| Skipping `facts.md` | You derive a command for the wrong package manager, init or firewall. |
| Checking only the current boot | The machine has been up for 50 minutes. You will not see last week's problem. Use `--since=-7d` and `-b -1`. |
