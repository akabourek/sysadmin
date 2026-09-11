---
name: next-steps
description: Use when the user asks what to do next on this machine - "what next", "what should I do", "recommend next steps", "where did we leave off", "where did we stop", "is anything else needed", "anything left to do" - or at the start of a session on a machine that already has reports, to decide whether anything is worth doing at all.
---

# Next steps

A review of **the report history of one machine**: what was done here, what
was left hanging, what has not been checked for a long time and what never
was. The output is a short ordered list of steps in the chat — or a sentence
saying there is nothing to do.

The skill **runs nothing, changes nothing and writes no report.** It does not
touch the live system either: all of its input is the repository. When the
honest answer is "only a check will tell you", the recommendation is that
check, not a way around it.

**Three principles the whole skill rests on:**

1. **A recommendation without a reference to a specific report is
   fortune-telling.** Every line cites a file and a date. "It would be good to
   check the disks" is not a recommendation; "SMART last run on 30 Aug, report
   `2026-08-30_1017-check.md`" is.
2. **An unresolved item has two honest endings: do it, or consciously close it
   in `NOTES.md`.** An item carried over by a third report is not a record, it
   is noise — and "close it" is a valid recommendation too.
3. **"Nothing to do" is a full-fledged output.** The skill has no quota of
   recommendations. When everything is taken care of, it says so and stops.
   Invented work is worse than none: it keeps the user busy, and next time the
   skill will be trusted less.

## Rules of engagement

| What | How |
|---|---|
| Reading the repository (`hosts/`, `playbooks/`, git log) | Directly, without asking. |
| Running `next_steps.py` | Directly. It reads only files in the repository. |
| Reading the live system | **Not done.** Diagnostics are the job of the recommended check, not of this skill. |
| Running a recommended skill or playbook | Only on the user's explicit instruction. A recommendation is not consent. |
| Any fix | Never. Always a separate task under CLAUDE.md §3a. |

## Procedure

### 0. Machine context

```bash
cat hosts/$(hostname)/facts.md hosts/$(hostname)/NOTES.md 2>/dev/null
```

For a machine managed over SSH (listed under `[remote]` in `hosts/sysadmin.toml`),
use its hostname instead of `$(hostname)`, here and in `--host`.

In `NOTES.md`, look for the **Accepted risks** section and for sentences such
as "deliberately not addressed", "user's decision", "leave as is". Headings
and notes in host files use the language from `hosts/sysadmin.toml`, so look
for the equivalent wording in that language. What has been decided there once
is not recommended again — unless the reason has changed, and then that change
has to be named.

When `hosts/$(hostname)/` does not exist, this skill has nothing to draw on.
Say so directly and recommend the one right thing: gather the facts about the
machine and run the first check.

### 1. Collection

```bash
python3 .claude/skills/next-steps/next_steps.py                # this machine
python3 .claude/skills/next-steps/next_steps.py --host host-2  # another machine in the repo
python3 .claude/skills/next-steps/next_steps.py --all          # findings from the whole history
python3 .claude/skills/next-steps/next_steps.py --days 180     # only the last half year
python3 .claude/skills/next-steps/next_steps.py --lang en      # override the report language
```

The report language comes from `language` in `hosts/sysadmin.toml` (`en` when
the file or key is missing); `--lang en|cs` overrides it. The script
recognises section headings **only in that language** — pointed at reports
written in another language, it finds no carried-over sections and no
findings. Report types are recognised by the file name suffix (`check`,
`security`, `leftovers`, `diagnostics`, `intervention`), which is English in
every language. Severity codes `P1–P4` and `R1–R4` are recognised, and so are
leftover confidence tiers in both forms (`C1–C4` in English, `J1–J4` in
Czech).

The script prints three blocks:

- **CADENCE** — when each report type last ran, how many times, and its
  severity totals. A type that never ran on the machine shows `NEVER`.
- **CARRIED-OVER SECTIONS** — the verbatim content of the sections *Left
  unresolved*, *What remains*, *Not checked*, *Not searched*, *Recommended
  next steps*, *Proposed fix order* and *Proposed cleanup order*, each with
  its source, age and how many reports were written after it.
- **FINDINGS** — findings tables; without `--all` only from the latest report
  of each type.

The script **only collects**. It does not pair findings with interventions
and recommends nothing.

### 2. Pairing — this is your job, not the script's

For every carried-over item and every finding, ask: **has anything happened to
it since?** The answer is in the later `*-intervention.md` reports and in
`NOTES.md`. Pairing is fuzzy — "finding #4 (pipewire)" in one report and
"silencing pipewire" in another are the same thing, but no regular expression
will connect them. That is why the model does it.

When you are not sure about a pairing, open both reports and read them. The
script output is a signpost, not a substitute for reading.

Sort the items into three buckets:

| Bucket | What to do with it |
|---|---|
| **resolved** | A later intervention closed it. It does not belong in the recommendations. |
| **consciously closed** | Rejected with a reason — "deliberately not addressed", *Accepted risks*. It does not belong until the reason changes. |
| **open** | Nobody touched it, or an intervention resolved it only partially. A candidate for a recommendation. |

### 3. Recommendation axes

A recommendation comes only from one of these five axes. What does not fit
any of them, do not recommend.

| Axis | Question | Evidence |
|---|---|---|
| **Never run** | Is there a check type that has never run on this machine? | `NEVER` in the cadence table |
| **Not run for a long time** | When was it last run? Has anything changed since that invalidates it? | date of the last run |
| **Carried-over item** | Has it been hanging over several sessions? | the section and the number of reports after it |
| **Trend tracking** | Did the report itself ask for a next measurement? | "compare on the next run…" |
| **Awaiting a decision** | Is it blocked by the user, not by the machine? | "user's decision" |

"Never run" is different from "not run for a long time" and weighs more: for
a check that never ran there is nothing to compare with and nobody knows what
is inside. On a machine with system check reports and not a single security
audit, that audit is the strongest recommendation, even if everything else is
clean.

Indicative cadence — **it is not a law**, just a point of reference. A machine
that has not changed does not need a check by the calendar:

| Type | Roughly | Sooner when |
|---|---|---|
| system check | a month | before and after a larger intervention, after a distribution upgrade |
| security audit | half a year | a new service, an opened port, a container, the machine going to a foreign network |
| application leftovers | half a year | after uninstalling a larger stack, before migrating the machine |

A stronger signal than the calendar is **a change since the last check**: a
kernel or distribution upgrade, new hardware, a new service, a new user. It
invalidates even a fresh report.

### 4. Building the order

Order by **urgency**, not by age:

1. Open P1/P2 or R1/R2 findings that no later intervention closed.
2. A check that has never run.
3. Things where a decision threatens to force itself (space running out on
   `/boot` before a kernel update, the distribution's end of support
   approaching).
4. A check that has not run for a long time, or that a change of the machine
   invalidated.
5. Items awaiting the user's decision.
6. Items that have been hanging so long that they should be closed in
   `NOTES.md`.

Keep it short. **Nobody does more than five recommendations** — when ten come
out, they are not recommendations, they are a copy of the history. Pick what
matters and sum up the rest in one sentence.

## When everything is taken care of

This is a normal state, not a failure of the skill, and after a well-run
session even the expected one. You recognise it like this:

- no open P1/P2 or R1/R2 finding,
- no check with `NEVER`,
- cadence is fine and the machine has not changed substantially since the last run,
- carried-over items are either resolved or consciously closed.

Then write exactly that, add **on what basis** you claim it and **when** it
makes sense to come back — and stop. No "just in case" list.

> There is nothing on this machine worth an intervention right now. The last
> system check ran on 30 Aug; all eight findings are either resolved or
> consciously closed in NOTES.md. The security audit is from 31 Aug,
> application leftovers from 30 Aug. It makes sense to come back after the
> next kernel upgrade or in about a month, whichever comes first.

Do not recommend just so the output is not empty. Specifically: do not remind
the user of a routine that ran yesterday; do not suggest running the other
skills "just in case"; do not make a recommendation out of a P4 finding marked
as noise in the report; and do not bring up again what is listed among the
accepted risks in `NOTES.md`.

## Output

Chat only, no file. A short summary and a table:

```markdown
History: 13 reports, 29 Aug – 31 Aug. Last system check 1 day ago.

| # | What to do | Why — evidence from the history | Open for |
|---|---|---|---|
| 1 | Run a security audit | Never run on this machine, yet a service account with a network service has been running since 28 Aug (NOTES.md) | — |
| 2 | Decide about the <size> of backups on the external disk | 2026-08-30_1019-leftovers.md, C1 — "decide", unchanged since | 2 sessions |
| 3 | Close the question of unmounted disks in NOTES.md | 2026-08-30_1040-intervention.md — "not searched for the third time in a row". Either mount them or exclude them from the search for good | 3 sessions |

Not recommending now: a system check (ran yesterday, 0× P1, 0× P2) or a
leftovers cleanup (30 Aug, resolved).
```

The **Open for** column counts sessions, not days — for an item that has
survived three sessions, that is the main argument. Always write the *Not
recommending now* part: it shows that the rest of the history was not
overlooked, only judged as done.

## After recommending

- Running anything is **the user's decision**. Offer, do not run.
- When the user closes an item ("stop dealing with this"), it belongs in that
  machine's `NOTES.md` under *Accepted risks* (headed in the language from
  `hosts/sysadmin.toml`) — otherwise the next run brings it up again.
- This skill does not create a report. When something is actually done in the
  same session, it is recorded in `*-intervention.md` as described in the
  `system-check` skill.

## Common mistakes

| Mistake | Why it matters |
|---|---|
| Producing a recommendation because one was expected | Breaks principle 3. An empty result is information, not a failure. |
| Recommending something a later intervention resolved | The script does not pair findings. Without step 2 it looks as if nothing was done in two days. |
| Reopening a consciously closed matter | `NOTES.md` has the reason. Either refute it with a specific change, or keep quiet. |
| Recommending ten things | Nobody does them and the important ones get lost. Five at most. |
| A recipe from the internet instead of a finding from the history | This skill may draw only on the repository. General advice without support in the reports does not belong here. |
| Running diagnostics "to be sure" | The recommendation is to run the check. Doing it here means doing it without the procedure written for it. |
| Running the recommended skill straight away | A recommendation is not consent. |
| Reading only the script output | The input is a signpost. Disputed items are verified in the report itself. |
| Treating cadence as a law | "A month since the last check" on an unchanged machine is not a reason. A change of the machine is. |
| Running the script with the wrong language | Headings are matched only in the configured language. Reports in another language yield no carried-over sections and no findings — check `hosts/sysadmin.toml` or pass `--lang`. |
