# sysadmin

A portable knowledge base and rule set for administering **modern desktop
Linux** with Claude. It is cloned onto every machine it is meant to look after.

It is not an automaton — it contains no scripts that run anything on their own.
The project lives in two git repositories.

This public repository contains:

- **rules** for how Claude behaves on a machine and what it must get approved
  ([CLAUDE.md](CLAUDE.md)),
- **procedures** written distro-agnostically ([`playbooks/`](playbooks/README.md)),
- **skills** — recurring workflows for Claude (`.claude/skills/`).

A private hosts repository, cloned into `hosts/` and ignored by this one,
contains:

- **facts about each machine** (`hosts/<hostname>/facts.md`),
- **notes and the history of interventions** on each machine
  (`hosts/<hostname>/NOTES.md`),
- **reports** from individual sessions (`hosts/<hostname>/reports/`),
- the **machine registry** (`hosts/README.md`) and tool settings
  (`hosts/sysadmin.toml`).

## Setup on a new computer

```bash
git clone https://github.com/<owner>/sysadmin.git ~/Projects/sysadmin
git clone git@github.com:<owner>/sysadmin-hosts.git ~/Projects/sysadmin/hosts
cd ~/Projects/sysadmin
claude
```

The public repository is read-only over HTTPS and needs no key. The hosts
repository is private and needs an SSH key with access to it.

Then just say: *"we are on a new machine, collect the facts"*. Claude asks
permission for the detection set, creates `hosts/<hostname>/`, writes the facts
and adds the machine to the registry in `hosts/README.md`. From then on it works
with what is actually on this particular computer. The `add-host` skill guides
the procedure.

**Without a hosts repository.** If you are starting out and have no hosts
repository of your own, create an empty one in place:

```bash
cd ~/Projects/sysadmin
git init hosts
```

Then add `hosts/README.md` with the registry table and `hosts/sysadmin.toml`
with the language of host files and reports:

```toml
language = "en"   # or "cs"
```

Claude creates both on the first run if you ask it to. If you want host data
backed up and shared between your machines, push the hosts repository to a
**private** remote. Never make it public ([CLAUDE.md](CLAUDE.md) §8).

**A machine without monitor and keyboard** is not managed remotely from another
computer. The procedure is the same, you just log in over `ssh` first and run
the clones and `claude` there. Logging in to Claude works without a browser as
well: it prints a link you open on another device. Clone the public repository
over HTTPS, without a key. Clone the hosts repository with a **deploy key that
has write access to `sysadmin-hosts` only**; GitHub deploy keys are unique per
repository. Such a machine cannot push to the public repository, so general
changes are pushed from a machine where you have your personal credentials.
This is a deliberate security boundary: a compromised headless box can alter
host data, but not the rules every machine executes. The `add-host` skill
guides the whole procedure.

## Supported environments

Nothing is hard-wired. It is built for what you run into on a modern desktop:

| Layer | Variants |
|---|---|
| Distribution | Fedora, Ubuntu/Debian, Arch, openSUSE, Silverblue/Kinoite |
| Package manager | `dnf5`, `apt`, `pacman`, `zypper`, `rpm-ostree`, `flatpak`, `snap`, `nix` |
| Desktop | KDE Plasma, GNOME, others; both Wayland and X11 |
| Init | systemd |
| Firewall | firewalld, ufw, nftables |
| LSM | SELinux, AppArmor |

## Machines

The registry of managed computers is `hosts/README.md`, in the private hosts
repository. This root README contains no hostname, because this repository is
published and `hosts/` never is ([CLAUDE.md](CLAUDE.md) §8).

A fresh clone of this repository has no machines — `hosts/` appears only when
you clone your hosts repository or create a new one. Each further machine is
added to the registry as soon as its `facts.md` exists; keeping the table
current is part of the rules ([CLAUDE.md](CLAUDE.md) §4).

## Skills

Workflows Claude can run on request (in any language):

| Skill | Purpose |
|---|---|
| `system-check` | review of logs and system health — "check the logs", "is something wrong" |
| `security-audit` | OS configuration from a security standpoint — "what is exposed", "are we leaky anywhere" |
| `app-leftovers` | orphaned configuration and leftovers from uninstalled software |
| `next-steps` | what to do next based on the machine's report history — "what next", "where did we leave off" |
| `add-host` | adding another machine, including a headless one over SSH — "add a machine", "we are on a new machine" |

## Security

Keys, passwords, tokens, certificates and the contents of `~/.ssh` and
`~/.gnupg` do not belong in either repository. `.gitignore` has a safeguard for
that, but the main safeguard is reviewing before every commit.

Concrete machine data (hostname, machine ID, addresses, account names, audit
findings) lives only in `hosts/<hostname>/`, in the private hosts repository;
general files use placeholder values (`host-1`, `user`). The hosts repository
is never made public, not even anonymised.

This repository is public. Both pushes, to the public and to the hosts
repository, need approval, and before every public push the outgoing commits
pass the private-data sieve from [CLAUDE.md](CLAUDE.md) §8b. The publishing
procedure is in [CLAUDE.md](CLAUDE.md) §8c.
