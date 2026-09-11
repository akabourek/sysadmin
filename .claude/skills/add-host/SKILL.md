---
name: add-host
description: Use when the user wants to add another computer to this repository - "add a machine", "add a host", "new computer", "onboard a host", "deploy to another machine", "set up on another computer", "installation guide", "we are on a new machine", "gather facts" - including a headless machine without monitor and keyboard reachable only over SSH, a machine where Claude Code cannot run and that is managed over SSH instead, or when running on a machine that has no hosts/<hostname>/facts.md yet.
---

# Add a host

How to get both repositories and Claude onto another computer and create its
`hosts/<hostname>/`. Installing the OS itself is out of scope.

- **Public repo `sysadmin`** — rules, playbooks, skills. Cloned over HTTPS
  without a key.
- **Private repo `sysadmin-hosts`** — cloned into `~/Projects/sysadmin/hosts`.
  The new machine commits its own facts there, with a deploy key.

**Two ways to manage a machine (CLAUDE.md §4), both valid; the user decides.**
*Locally*: the user logs in, clones both repositories and starts Claude on the
machine, and the rules apply unchanged (procedures A and B). *Over SSH*: Claude
stays on the machine it runs on and reaches the new one with `ssh`; nothing is
cloned there (procedure C). Over SSH is the only option where Claude Code
cannot run (it needs x64 or ARM64 and at least 4 GB of RAM), and a sensible one
for a small appliance.

**Security boundary.** In local management the new machine gets a deploy key with write access to
`sysadmin-hosts` only. GitHub deploy keys are unique per repository, so it
cannot push to the public repo. General changes (rules, playbooks, skills) are
pushed from a machine where the user has personal credentials. This is
deliberate: a compromised headless box can alter host data, but not the rules
every machine executes. Over SSH the machine gets no key and no clone at all.

## Where am I

| Situation | How to tell | Procedure |
|---|---|---|
| The new machine is a **different computer** from the one I run on | The user names another hostname, address or SSH alias | **A** |
| The new machine will be **managed over SSH** from the machine I run on | A2 shows an architecture other than x86_64/aarch64, a 32-bit userland or less than 4 GiB of RAM, or the user chooses it | **A1, A2, then C** |
| I am running **on the new machine** | `ls hosts/$(hostname)/facts.md` fails | **B** |
| `facts.md` exists | — | This skill is not needed. Only update the facts when they are stale (§4). |

## Rules of engagement

| What | How |
|---|---|
| Reading on this machine without network (`getent hosts`, `ssh -G`, `ssh-keygen -F/-lF`, `git remote`, `git status`, also with `git -C hosts`) | Directly. |
| Anything over the network: `ssh` to the new machine (even read-only), `gh`, `git ls-remote`, `git fetch/pull/push` in either repo | §3a / §7, approval beforehand. |
| Installing packages or Claude, creating a key, cloning on the new machine | **The user does it.** I prepare the exact commands. |
| Adding the deploy key on GitHub (`gh repo deploy-key add`) | §3a. The *impact* must say: a key with write access may push to any branch of `sysadmin-hosts`, including `main`, so whoever takes over the new machine can rewrite host data for every machine (facts, notes, reports, the registry), for example add an accepted risk that hides a finding. It cannot touch the rules and skills in the public repo. Rollback: delete the key in `sysadmin-hosts` Settings → Deploy keys. |
| Detection set on the new machine | §4, approval beforehand. For a new machine §4 is more specific than §3b. |
| Read-only diagnostics without root over SSH on a machine listed under `[remote]` in `hosts/sysadmin.toml` | Directly, as §3b (CLAUDE.md §4). Before the machine is listed, every connection is §3a. |

## A. Preparation from another machine

### A1. Local reading

```bash
getent hosts host-2.local
ssh -G host-2 | grep -E '^(hostname|user|port|forwardagent|stricthostkeychecking) '
ssh-keygen -F host-2.local | grep -v '^#' | awk '{print $(2)}'   # empty = first contact
git remote get-url origin; git status -sb                        # public repo
git -C hosts remote get-url origin; git -C hosts status -sb      # hosts repo
ssh-keygen -lF github.com | grep -i ed25519                      # fingerprint for the clone step
```

**Read SSH settings through `ssh -G <alias>`, never by grepping the whole
`~/.ssh/config`.** Users write passwords into comments in the config. Grep
prints them; `ssh -G` prints only what actually applies to the given alias.

- **`main` ahead of `origin/main`, in either repo** → the new machine will not
  get those commits. Get the push approved before the clone. In the public
  repo that means the §8b sieve over `git diff origin/main..HEAD` and the
  commit messages first, and the push only from a machine with the user's
  personal credentials. If this machine is itself headless, it cannot push
  the public repo. Say so and let the user push from elsewhere.
- **The public repo** is cloned on the new machine over HTTPS, whatever remote
  this machine uses. Derive the URL from `origin`:
  `https://github.com/<owner>/sysadmin.git`.
- **The hosts remote is not `git@github.com:`** → for another SSH hosting,
  substitute its domain and its deploy keys. For an HTTPS hosts remote this
  procedure does not apply. Say so and agree on an approach.
- **`hosts/` is not a repository of its own** (`git -C hosts remote` prints
  the public URL or fails) → this machine has no hosts repo to hand over.
  Stop and sort that out first; do not continue with a single repository.
- **The new machine's key is not in `known_hosts`** → A2 fails in
  `BatchMode`. The user has to log in manually once. A machine without a
  monitor has nowhere to show the fingerprint, so the user either verifies it
  through another channel (installer output, the console during
  installation), or knowingly accepts it on first connection in a home LAN.
  Whichever it was, record it in `NOTES.md` during B. When the machine is
  reached with a password, skip A2 and let the user run the same lines after
  logging in.

### A2. Prerequisite check over SSH (§3a)

Substitute `<owner>` before running: the heredoc is quoted, so nothing inside
is expanded here.

```bash
ssh -a -o BatchMode=yes host-2 bash -s <<'EOF'
echo "host: $(hostname)"
. /etc/os-release; echo "os: $PRETTY_NAME"
echo "arch: kernel $(uname -m), userland $(getconf LONG_BIT)-bit"
echo "mem: $(awk '/^MemTotal:/ {printf "%.1f GiB", $(2)/1048576}' /proc/meminfo)"
for b in git curl tmux sudo; do echo "$b: $(command -v $b || echo missing)"; done
echo "claude: $(command -v claude || ls ~/.local/bin/claude 2>/dev/null || echo missing)"
echo "groups: $(id -Gn)"
echo "repo: $(ls -d ~/Projects/sysadmin 2>/dev/null || echo none)"
echo "hosts: $(git -C ~/Projects/sysadmin/hosts rev-parse --show-toplevel 2>/dev/null || echo none)"
echo "keys: $(cd ~/.ssh 2>/dev/null && ls *.pub 2>/dev/null | tr '\n' ' ')"
echo "public: $(GIT_TERMINAL_PROMPT=0 git ls-remote https://github.com/<owner>/sysadmin.git HEAD </dev/null >/dev/null 2>&1 && echo ok || echo failed)"
echo "github: $(ssh -n -a -o BatchMode=yes -o StrictHostKeyChecking=yes -T git@github.com 2>&1 \
  | grep -m1 -E '^Hi |Permission denied|host key is known|Host key verification failed|Could not resolve|Connection')"
k=~/.ssh/sysadmin-hosts-deploy
if [ -f "$k" ]; then
  err=$(GIT_SSH_COMMAND="ssh -i $k -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes" \
    git ls-remote git@github.com:<owner>/sysadmin-hosts.git HEAD 2>&1 >/dev/null </dev/null) \
    && echo "hosts-access: ok" || echo "hosts-access: ${err%%$'\n'*}"
else echo "hosts-access: no deploy key"; fi
EOF
```

Why it is written exactly like this:

- `bash -s` — the remote login shell may be fish.
- `-a` — without an agent, the inner ssh and git cannot get through with the personal key from this machine.
- `-n` on the inner ssh — otherwise it swallows the rest of the script from stdin.
- `</dev/null` on git — for the same reason: nothing inside may read the script.
- `GIT_TERMINAL_PROMPT=0` — an HTTPS repo that is not public would otherwise ask for a user name.
- `ls ~/.local/bin/claude` — ssh with a command does not read `~/.profile`, so `command -v` does not see a native install.
- Two access tests — before a deploy key exists, only `ssh -T git@github.com` is possible, and it reports just **which key authenticated** (a personal key, a deploy key of some repository, or none). Once `~/.ssh/sysadmin-hosts-deploy` exists, `git ls-remote` against the hosts URL with exactly that key is the precise test. Neither proves write access; that shows at the first push in B.

`BatchMode` only forbids prompts. `UpdateHostKeys` may add further keys of an
already known machine to `known_hosts`. That is fine, just do not claim that
nothing gets written.

| Output | Meaning |
|---|---|
| No `host:` line | The connection to the new machine already failed. The lines below mean nothing → A1, first contact. |
| `arch:` other than `x86_64`/`aarch64`, or `userland 32-bit` | Claude Code cannot run there. A 64-bit kernel with a 32-bit userland is common on Raspberry Pi OS. Tell the user: the options are a 64-bit reinstall, or management over SSH → C. |
| `mem:` below 4 GiB | Below the documented minimum for Claude Code. Tell the user; management over SSH (C) avoids it. |
| `public: failed` | The public repo cannot be read anonymously over HTTPS: not published yet, wrong `<owner>`, no network, or `git: missing`. Say so and agree on a fix. Do not work around it with a personal key on the machine. |
| `repo:` present, `hosts: none` | Only the public repo is cloned. Continue with the hosts clone (stage 3). |
| `hosts:` prints a path other than `…/Projects/sysadmin/hosts` | `hosts/` exists but is not its own repository, so git fell through to the parent. Stop and find out what it is before cloning into it. |
| `github: Hi <owner>/sysadmin-hosts!` | A default key is already the deploy key of the hosts repo. Clone with that key. |
| `github: Hi <owner>/<other repo>!` | A deploy key of another repository. It cannot be reused for `sysadmin-hosts` → new deploy key. |
| `github: Hi <user>!` | A **personal** key sits on the machine, reaching every repository of the user, including a push to the public repo. It works, but it breaks the security boundary. Ask whether that is intended and offer a deploy key. |
| `github: Permission denied` | No default key is accepted. The usual state → deploy key. |
| `github: No … host key is known` / `Host key verification failed` | GitHub is not in `known_hosts` yet, access not verified. No `.pub` in `keys:` → deploy key. |
| `hosts-access: ok` | The deploy key reads `sysadmin-hosts`. Clone. |
| `hosts-access: ERROR: Repository not found.` / `…Permission denied…` | The key exists but is not added to `sysadmin-hosts` (or went to another repository) → stage 2. |
| `hosts-access: no deploy key` | → stage 1, step 5. |
| `groups:` without `wheel`/`sudo`, or `sudo: missing` | Root on the machine is obtained through `su`. Adjust the commands for the user accordingly. |

### A3. Handoff to the user, in three stages

It cannot be done in one block; a manual step waits between the stages. Skip
whatever is already done.

**Stage 1 — on the new machine**
1. `ssh host-2`
2. Missing `git`, `curl`, `tmux` from the distribution package manager (derive
   it from `os:`), through `sudo`, or `su -c '…'` when there is no sudo.
3. `tmux new -s sysadmin`. After a dropped connection: `ssh -t host-2 tmux attach -t sysadmin`.
4. Public repo, no key needed:
   ```bash
   git clone https://github.com/<owner>/sysadmin.git ~/Projects/sysadmin
   ```
5. Deploy key for the hosts repo:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/sysadmin-hosts-deploy -C "host-2 sysadmin-hosts" -N ''
   cat ~/.ssh/sysadmin-hosts-deploy.pub
   ```

**Stage 2 — GitHub.** The user adds the public key on the web **in the
`sysadmin-hosts` repository** (Settings → Deploy keys, *Allow write access*),
or pastes the content of the `.pub` into the chat. I save it to the scratchpad
and, after §3a, run
`gh repo deploy-key add <scratchpad>/host-2.pub -R <owner>/sysadmin-hosts --allow-write --title host-2`.
Write access is needed because the new machine commits its own facts. The key
never goes to the public repo `sysadmin`: with write access there, the machine
could rewrite the rules for everyone.

**Stage 3 — back on the new machine**
```bash
cd ~/Projects/sysadmin
GIT_SSH_COMMAND='ssh -i ~/.ssh/sysadmin-hosts-deploy -o IdentitiesOnly=yes' \
  git clone git@github.com:<owner>/sysadmin-hosts.git hosts
git -C hosts config core.sshCommand 'ssh -i ~/.ssh/sysadmin-hosts-deploy -o IdentitiesOnly=yes'
git -C hosts config user.name '<name>'; git -C hosts config user.email '<email>'
```
- The user compares the GitHub fingerprint the clone asks about with the
  output of `ssh-keygen -lF github.com` from A1. Copy the value out for them.
  When it does not match, they answer `no`.
- Set the git identity only in the hosts repo, where the machine commits.
  Without it the first commit on the machine fails. The public repo gets no
  identity: this machine does not commit there.
- The public repo keeps its HTTPS remote. `git pull` works without
  credentials; `git push` fails, and that is intended.
- When a repository already exists, do not clone again. `git pull`
  (or `git -C hosts pull`) is enough.
- Claude Code is installed according to the official documentation. The
  installer is `curl | sh`, so the user runs it. When `claude` is then not in
  `PATH`, opening a new tmux window (`Ctrl-b c`) is enough.
- After starting `claude` (in `~/Projects/sysadmin`), the login without a
  browser prints a link. The user opens it on another device.
- Finally, type on the machine: *"we are on a new machine, gather facts"* →
  procedure B.

In local management the work on this machine ends here. Do not write facts of
another machine from here; that is done in B, on the machine itself.

## B. First session on the new machine

1. **Both repositories.** `git remote get-url origin` shows the HTTPS URL of
   the public repo, and `git -C hosts rev-parse --show-toplevel` ends in
   `/hosts`. When `hosts/` is missing or is not its own repository, stage 3 of
   A was not done: stop and hand it back to the user. Never run
   `git init hosts` here; that is only for a newcomer who has no hosts repo
   at all.
2. **Name.** The directory is named exactly after the output of `hostname`.
   The same name goes into the `hostname` key in the JSON for the report
   generators. It must not be the `.local` name or the SSH alias.
   **Stop and ask when** the name is generic (`localhost`, `debian`,
   `fedora`, `ubuntu`, `raspberrypi`, …) or when `hosts/<hostname>/` already
   exists with a different machine ID. Renaming through `hostnamectl` is §3a.
3. **One approval at the start** for pulling both repositories (§7) and the
   detection (§4). The pull must happen before the registry is edited,
   otherwise the table conflicts. Pulling the public repo gives the machine
   the current rules and skills.
   ```bash
   git pull && git -C hosts pull
   mkdir -p tmp && bash .claude/skills/add-host/detect.sh > tmp/detect.txt 2>&1
   ```
4. **Language.** Read `language` from `hosts/sysadmin.toml` (missing file or
   key → `en`). `facts.md` and `NOTES.md` are written in that language,
   headings included. The conversation stays in the user's language.
5. **Root reading in one line (§3b)** for what the detection cannot see
   without root: the firewall rules and the effective sshd configuration
   (`sshd -T`). On a machine without a monitor both back the sentence about
   the only access. When the machine has no sudo, hand the block over with
   `su -c`.
6. **Ask the user about access.** The detection does not collect where the
   machine is reached from, through which alias, with which account, or
   whether with a key or a password.
7. **`hosts/<hostname>/facts.md`** — a header with the date of detection, then
   sections. The section names below are in English; headings in host files
   use the language from `hosts/sysadmin.toml`.
   - *System*
   - *Hardware* — on ARM, the model from device-tree
   - *Boot and storage* — RAID and ZFS, if present
   - *Desktop*; on a machine without a monitor, *No desktop* instead
   - *System management* — package managers, repositories, automatic updates,
     containers, init, firewall, LSM
   - *Network*
   - *User* — **including how root is obtained: sudo, or su**
   - *Access* — only on a machine without a monitor
   - *What this means for interventions*

   Whatever is not in the output, record as *not detected*; do not guess. On a
   machine without a monitor, *What this means for interventions* must say:
   **an intervention in sshd, the firewall or the network can cut off the
   only access. It is done only with a second session open, and the new
   session is verified before the old one is closed.**
8. **`hosts/<hostname>/NOTES.md`** — the date the machine was added. Then the
   name of the deploy key and its rights (write, `sysadmin-hosts` only),
   `core.sshCommand` in `hosts/.git/config`, the fact that the public repo is
   cloned over HTTPS and cannot be pushed from here, and on first contact also
   how the fingerprint of the machine key was verified.
9. **The row in `hosts/README.md`** — the registry in the hosts repo — belongs
   in the machine's commit. It concerns only this machine (§7).
10. **Before the commit:**
    - Review `git -C hosts diff --cached`.
    - `git -C hosts diff --cached | grep -i 'PRIVATE KEY'` must return nothing.
    - `git -C hosts config user.email` must exist.
    - `git status -sb` in the public repo shows no changes. Anything general
      that came up is reported to the user, not committed here.
    - Subject: `<hostname>: <facts about a new machine>`, written in the hosts
      language like everything else in the hosts repository.
11. **Push** after approval (§7): `git -C hosts push`. A rejection for
    missing write access means the key was added without *Allow write
    access*.
12. **Cleanup:** delete `tmp/detect.txt` and the outputs of the root reading.
    They contain the machine ID, addresses and ports.
13. Offer a first check (`system-check`). Do not run it.

## C. Managed over SSH

The machine is reached from the machine I run on. Nothing is installed or
cloned on it for this. A1 and A2 are already done.

1. **Record the decision** in `hosts/sysadmin.toml`:
   ```toml
   [remote]
   host-2 = "host-2.local"   # hostname = "ssh alias"
   ```
   The key is the output of `hostname` from A2 (`host:`), never the alias.
   Check that the alias really leads to that machine: an alias with a similar
   name can point somewhere else in `~/.ssh/config`, and `host:` in A2 is the
   proof. From now on read-only diagnostics over SSH on it are §3b.
2. **One approval** for pulling the hosts repo (§7) and the detection (§4):
   ```bash
   git -C hosts pull
   mkdir -p tmp && ssh -a -o BatchMode=yes host-2.local bash -s \
     < .claude/skills/add-host/detect.sh > tmp/detect-host-2.txt 2>&1
   ```
3. **Root reading in one line (§3b)**, run by the user because of sudo:
   ```bash
   ssh -t host-2.local 'sudo nft list ruleset; sudo sshd -T' 2>&1 | tee tmp/root-host-2.txt
   ```
   Without sudo on the machine, use `su -c '…'` inside the quotes.
4. **Facts, notes, registry, commit** as B steps 4 and 6–12, with these
   differences:
   - *Access* in `facts.md` says: managed over SSH, from which machine or
     machines, alias, account, key or password, and why SSH (for example
     "32-bit userland, Claude Code cannot run").
   - `NOTES.md` records that no repository and no deploy key live on the
     machine, and how the fingerprint of the machine key was verified if this
     was the first contact.
   - The commit (`hosts/sysadmin.toml`, the host directory, the registry row)
     and the push are done here with `git -C hosts`. The public repo stays
     untouched.
5. **Cleanup:** delete `tmp/detect-<hostname>.txt` and `tmp/root-<hostname>.txt`.
6. Offer a first check (`system-check`), run over SSH with the hostname given
   explicitly. Do not run it.

## Common mistakes

| Mistake | Why it hurts |
|---|---|
| Choosing the mode for the user, or managing a machine over SSH without its `[remote]` entry | Both modes are valid and the choice is the user's. Without the entry, SSH reads have no §3b cover and the other machines do not know how the host is managed. |
| Grepping the whole `~/.ssh/config` | Prints passwords from comments. Use `ssh -G <alias>`. |
| Assuming the clone will succeed | The private hosts repo over SSH needs a key on the new machine; the HTTPS clone of the public repo needs it to be actually public. Verify in A2. |
| A2 without `-a` | With `ForwardAgent yes`, the inner ssh and git get through with the personal key and the result lies. |
| Copying a personal private key to the new machine or enabling agent forwarding | A deploy key reaches one repository and can be revoked on its own. A personal key could also push to the public repo. |
| Taking `claude: missing` from ssh as certain, without checking `~/.local/bin` | Non-interactive ssh does not read `~/.profile`. |
| Cloning while `main` is not pushed, in either repo | The new machine gets older rules and skills, or an older registry and host data. |
| Naming the directory after the `.local` name, the alias or a generic hostname | Skills do not find the machine, or two machines merge into one directory. |
| Counting on `sudo` on Debian | When a root password was set during installation, there is no sudo. |
| Installing packages or Claude for the user | Root and `curl \| sh` always go through the user (§0, §3a). |
| `git -C hosts pull` only after editing `hosts/README.md` | Two machines add a row to the same table, a conflict follows. |
| Pulling only one repository at the start | Rules and host data drift apart, and the registry can still conflict. |
| Forgetting the row in `hosts/README.md` | The machine is invisible to the other computers. |
| On a machine without a monitor, leaving out the sentence about the only access | The next firewall intervention cuts the machine off and nobody can reach it. |
| Leaving `tmp/detect.txt` lying around | Machine ID, addresses and ports must not outlive the session. |
| Cloning only one repository | Without `hosts/`, skills find no facts and `git -C hosts` falls through to the public repo. Without the public repo, there are no rules or skills at all. |
| `git init hosts` on a machine joining an existing setup | A separate history with its own registry that cannot be pushed to `sysadmin-hosts` without a conflict. `git init hosts` is only for a newcomer with no hosts repo. |
| Adding the deploy key to `sysadmin` instead of `sysadmin-hosts` | The hosts clone fails, and with write access the machine could rewrite the rules for every machine. |
| Cloning the public repo over SSH with the deploy key | The key belongs to `sysadmin-hosts` only; GitHub answers `Repository not found`. The public repo is cloned over HTTPS. |
| Pushing general changes from a headless machine (personal key, stored token, write key on the public repo) | Breaks the security boundary: a compromised box could alter the rules every machine executes. General changes go from a machine with the user's personal credentials, after the §8b sieve. |
| Committing host data with plain `git` instead of `git -C hosts` | `hosts/` is ignored by the public repo, so nothing is committed; with `git add -f`, host data lands in the published repository. |
| Taking `Hi <owner>/sysadmin-hosts!` or `hosts-access: ok` as proof of write access | Both show read access only. Write access shows at the first push. |
| Skipping the `arch:` and `mem:` lines in A2 | The mismatch shows only when Claude fails to install on the machine, a whole round too late. |
| Using `$(hostname)` or running a skill's commands locally for a machine under `[remote]` | The report lands in the wrong host directory and the findings describe the wrong machine. |
| Piping a root script into `ssh … sudo bash -s` | sudo reads the password from the same terminal and swallows the script. Copy the script over first, then run it with `ssh -t`. |
