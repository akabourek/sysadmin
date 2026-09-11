# Playbooks

Repeatable procedures, written **distro-agnostically**. A playbook says *what*
to do and in which order; the concrete command is derived from
`hosts/<hostname>/facts.md`.

Rules for writing a playbook:

- Start with diagnostics, not with an intervention.
- For every step, state what is verified after it is done.
- State the rollback.
- Do not write one distribution's commands as if they were universal — either
  generalize, or give a table of variants.
- Do not write anything here that contains passwords or keys.
