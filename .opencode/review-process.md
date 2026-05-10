# Code Review Protocol

## Pre-commit Mandatory Review

Before executing `git commit` for any development task, you MUST follow this review loop:

### Review Loop

1. Run the initial review:
   ```bash
   bash scripts/codex-review.sh
   ```

2. Read the Codex review output carefully.

3. If the review result is **REJECTED** (exit code 1):
   - Note the `SESSION_ID` from the output
   - Make the necessary fixes based on Codex's feedback
   - Re-run with the session ID to continue the same review context:
     ```bash
     bash scripts/codex-review.sh <SESSION_ID>
     ```
   - Repeat until you get **APPROVED**

4. If the review result is **APPROVED** (exit code 0):
   - You may now proceed to `git commit`

### Rules

- Only trigger one review cycle per independent feature/task, not per file change.
- Never skip the review loop. If `codex-review.sh` fails with exit code 2 (Codex error), inform the user and ask how to proceed.
- Do not modify `scripts/codex-review.sh` or this instruction file during normal development.
