# Verification Checklists

## Always

- Confirm the files you changed are the files that should change.
- Run the smallest relevant verification that can falsify the change.
- Report skipped checks explicitly.

## P1

- State assumptions and success criteria.
- Run at least one relevant executable check.
- Review the final diff for obvious regressions.

## P2

- Re-read the surrounding code before editing.
- Break the task into small, independently verifiable steps.
- Run the relevant test suite, not just a smoke test.
- Check edge cases, error paths, and any touched interfaces.

## P3

- Reproduce the bug or bound the failure mode before patching.
- Keep the patch minimal and reviewable.
- Prefer rollback-safe changes.
- Stop and report uncertainty if verification is inconclusive.

## Risk multipliers

Add extra caution for:

- migrations or schema changes;
- auth, permissions, or security-sensitive paths;
- billing, payments, or destructive operations;
- concurrency, caching, or distributed coordination;
- areas with no existing automated tests.
