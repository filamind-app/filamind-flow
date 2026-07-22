# DeltaFabs team

Maintainers' note. Nothing here is needed to use, build, or contribute to this project - see the
README and CONTRIBUTING for that.

FilaMind is built and maintained by the DeltaFabs team:

- Abdelmonem Awad - <eg2@live.com>
- Ahmed Bebars - <Ahmedbebars1@gmail.com>
- Kareem Salama - <Golden.kiko@gmail.com>

## Maintainer workspace

The team keeps its working material - the handbook, the current handoff, and the planning and
research corpus - in a private repository:

**`filamind-app/filamind-internal`** (private; requires organization access)

```bash
git clone https://github.com/filamind-app/filamind-internal.git
```

Read the newest file in `handoffs/` before starting work: it records what shipped, what is still
open, and what each open item is waiting on. `handbook/rules.md` and `handbook/sync-protocol.md`
carry the working rules.

## Recording changes

Work on this repository is not finished when the code merges - it is finished when the workspace
records that it merged. Several maintainers and sessions work in parallel, and that record is how
they stay in agreement about the state of the project.

After shipping anything here, update the newest handoff in the workspace:

- **A release published** - add a changelog line and the new version to the state table.
- **An issue answered, fixed, or closed** - update its row, saying exactly what is now being waited
  on and by whom.
- **A new issue or pull request you did not resolve** - add a row with what it is blocked on.
- **Something learned the hard way** - add it to `handbook/rules.md` with the reason it matters, or
  to `handbook/ci-and-release.md` if it is a build or release mechanic.

Two rules make the record trustworthy:

**Verify before recording.** Check `gh release list`, `gh issue list`, `gh pr list` and
`git log origin/main` rather than writing down what you remember. If the workspace contradicts
reality, correct it and say so in the commit - a wrong state table is worse than a missing one,
because the next person acts on it.

**Never record state you did not check.** If you did not confirm that CI passed, write that it is
unverified rather than assuming.

Record what is true, not what is planned: work in progress and unmerged pull requests do not belong
in the record.
