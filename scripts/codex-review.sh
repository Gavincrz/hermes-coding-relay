#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
WORK_DIR="/tmp/codex-reviews"
mkdir -p "$WORK_DIR"

SESSION_ID="${1:-}"
OUT_FILE="$WORK_DIR/response-$$.txt"

if [ -z "$SESSION_ID" ]; then
    if git -C "$PROJECT_DIR" diff --quiet HEAD 2>/dev/null; then
        echo "APPROVED - No changes to review."
        exit 0
    fi
fi

if [ -n "$SESSION_ID" ]; then
    codex exec resume "$SESSION_ID" \
        -o "$OUT_FILE" \
        "开发者已根据你的审查意见修改了代码。请用 git diff 重新审查当前的 uncommitted 变更。

如果所有问题已解决，回复的第一行必须是：
## APPROVED

如果仍有问题，回复的第一行必须是：
## REJECTED
然后列出具体修改意见。" \
        2>/dev/null >/dev/null || true
else
    codex exec --sandbox read-only \
        -o "$OUT_FILE" \
        "你是代码审查员（只读模式，不要修改任何文件）。请审查当前仓库的 uncommitted 变更。

工作流程：
1. 用 git diff 查看变更内容
2. 如需理解上下文，可以读取项目中任何文件
3. 检查是否符合 best practice、有无 bug、代码质量如何

回复格式要求：
- 如果一切没问题，回复的第一行必须是：## APPROVED
- 如果有问题，回复的第一行必须是：## REJECTED，然后列出具体修改意见" \
        2>/dev/null >/dev/null || true

    NEWEST=$(find ~/.codex/sessions -name "*.jsonl" -printf '%T@\t%p\n' 2>/dev/null \
        | sort -rn | head -1 | cut -f2)
    if [ -n "$NEWEST" ]; then
        SESSION_ID=$(basename "$NEWEST" \
            | sed -n 's/.*\([0-9a-f]\{8\}-[0-9a-f]\{4\}-[0-9a-f]\{4\}-[0-9a-f]\{4\}-[0-9a-f]\{12\}\).*/\1/p')
    fi
fi

if [ ! -f "$OUT_FILE" ] || [ ! -s "$OUT_FILE" ]; then
    echo "ERROR: Codex did not return a response."
    echo "SESSION_ID=${SESSION_ID:-unknown}"
    exit 2
fi

RESPONSE=$(cat "$OUT_FILE")
rm -f "$OUT_FILE"

echo "$RESPONSE"
echo ""

FIRST_LINE=$(echo "$RESPONSE" | head -1 | xargs)
FIRST_LINE="${FIRST_LINE#\#\# }"
if [ "$FIRST_LINE" = "APPROVED" ]; then
    echo "=== REVIEW PASSED ==="
    echo "SESSION_ID=N/A (approved)"
    exit 0
else
    echo "=== REVIEW REJECTED ==="
    echo "SESSION_ID=${SESSION_ID:-unknown}"
    echo ""
    echo "Fix the issues above, then re-run:"
    echo "  bash scripts/codex-review.sh ${SESSION_ID:-<SESSION_ID>}"
    exit 1
fi
