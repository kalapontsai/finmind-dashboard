#!/bin/bash
# FinMind No-LLM heartbeat
# 讀 finmind-iter.md → 抓下一個 [ ] → 跑對應腳本 → git commit/push → openclaw message send
# 完全不用 LLM。失敗 → Telegram 收 error log
#
# Cron 設定（範例：每 30 分鐘）：
#   */30 * * * * /bin/bash /mnt/d/.../finlab_tw_screener/scripts/finmind-heartbeat.sh
#
# 環境變數：
#   FINMIND_CHAT_ID  Telegram chat_id（default: 8774080801 = 大大）

set -e

# ───────── config ─────────
ITER_FILE="$HOME/.openclaw/workspace-two/finmind-iter.md"
PROJECT_DIR="/mnt/d/OneDrive - Sampo Corporation/3.Data/5.Python/finlab_tw_screener"
SCRIPTS_DIR="$PROJECT_DIR/scripts/v14"
LOG_DIR="$HOME/.openclaw/workspace-two/logs"
LOG_FILE="$LOG_DIR/finmind-heartbeat.log"

CHAT_ID="${FINMIND_CHAT_ID:-8774080801}"

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*" | tee -a "$LOG_FILE"
}

notify() {
    # $1 = message
    openclaw message send --channel telegram --target "$CHAT_ID" --message "$1" 2>> "$LOG_FILE" || \
        log "WARN: openclaw message send failed: $1"
}

# ───────── 取得下一個待辦 ─────────
# 抓 "- [ ] **P[N]-[M]**..." 或 "- [ ] **P[N]-[M] 描述**..." 第一個匹配的 P-id
ITEM_ID=$(grep -E "^- \[ \] \*\*P[0-9]+-[0-9]+" "$ITER_FILE" 2>/dev/null \
    | head -1 \
    | grep -oE 'P[0-9]+-[0-9]+')

if [ -z "$ITEM_ID" ]; then
    log "no pending item (all [ ] cleared)"
    notify "FinMind heartbeat: 全部 [ ] 都清完了，等待 P3 review 新增項目"
    exit 0
fi

log "picked item: $ITEM_ID"

# ───────── 找對應腳本 ─────────
SCRIPT_FILE="$SCRIPTS_DIR/${ITEM_ID}.py"
if [ ! -f "$SCRIPT_FILE" ]; then
    log "ERROR: script not found: $SCRIPT_FILE"
    notify "FinMind heartbeat: $ITEM_ID 找不到對應腳本 $SCRIPT_FILE"
    exit 1
fi

# ───────── 跑腳本（在專案目錄下）─────────
cd "$PROJECT_DIR"
log "running: python3 $SCRIPT_FILE"
if ! python3 "$SCRIPT_FILE" >> "$LOG_FILE" 2>&1; then
    log "ERROR: $ITEM_ID script failed (exit $?)"
    notify "FinMind heartbeat: $ITEM_ID 跑失敗，看 log $LOG_FILE"
    exit 1
fi
log "$ITEM_ID script OK"

# ───────── git add / commit / push ─────────
# 分開 add（不會因為一個路徑不存在讓全部失敗）
for d in scripts routes lib static templates quant tests; do
    [ -d "$d" ] || continue
    git add "$d/" 2>> "$LOG_FILE" || log "WARN: git add $d/ 失敗"
done
git add scripts/finmind-heartbeat.sh 2>> "$LOG_FILE" || true
git add scripts/v14/ 2>> "$LOG_FILE" || true

# 不要 commit 沒變更
if git diff --cached --quiet; then
    log "no staged changes, skip commit"
else
    git commit -m "feat(v14): $ITEM_ID — 心跳自動完成 $(date '+%Y-%m-%d %H:%M')" >> "$LOG_FILE" 2>&1
    COMMIT=$(git rev-parse --short HEAD)
    log "committed: $COMMIT"
    # push 失敗不致命（local commit 已存）
    git push origin main 2>> "$LOG_FILE" || log "WARN: push failed (will retry next run)"
fi

# ───────── 標記 iter [x] ─────────
# 用 awk 安全替換第一個匹配（依 ITEM_ID）
TEMP_FILE=$(mktemp)
awk -v id="$ITEM_ID" '
    /^- \[ \] \*\*P[0-9]+-[0-9]+/ && index($0, "**" id) {
        sub(/^- \[ \]/, "- [x]")
    }
    { print }
' "$ITER_FILE" > "$TEMP_FILE" && mv "$TEMP_FILE" "$ITER_FILE"
log "marked $ITEM_ID as [x] in iter file"

# ───────── 回報 ─────────
notify "✅ v1.4 $ITEM_ID 跑完$( [ -n "$COMMIT" ] && echo "（commit $COMMIT）" )"
log "=== $ITEM_ID done ==="
