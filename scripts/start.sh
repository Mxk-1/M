#!/usr/bin/env bash
# A 股系统薄壳启动脚本：包裹 conda run，省去日常敲长命令。
set -euo pipefail

# 无论从哪个 cwd 调用，都切到仓库根再执行
cd "$(dirname "$0")/.."

DB="a_share_system/market.duckdb"
DIST="a_share_system/web/frontend/dist/index.html"

usage() {
  cat <<'EOF'
用法: ./scripts/start.sh [命令]
  serve    只启动 Web，http://localhost:8080（默认）
  daily    盘后一条龙：update → run → serve
  update   仅拉当日/缺口数据
  run      仅扫描策略信号
EOF
}

# 统一入口：调用 a_share_system.main 的某个 mode
py() { conda run --no-capture-output -n mxk_env python -u -m a_share_system.main "$1"; }

# 锁检查：lsof 无匹配时退出码非 0，故 `|| true` 兜底
check_lock() {
  local holder
  holder=$(lsof -t "$DB" 2>/dev/null || true)
  if [ -n "$holder" ]; then
    echo "✗ 数据库被占用，先停掉这些进程：" >&2
    lsof "$DB" 2>/dev/null | awk 'NR>1 {print "  PID="$2, $1}' >&2
    exit 1
  fi
}

# 前端检查：dist 不存在则提示先构建
check_frontend() {
  if [ ! -f "$DIST" ]; then
    echo "✗ 前端未构建，先执行：cd a_share_system/web/frontend && npm install && npm run build" >&2
    exit 1
  fi
}

case "${1:-serve}" in
  serve)  check_lock; check_frontend; py serve ;;
  daily)  check_lock; check_frontend; py update; py run; py serve ;;
  update) check_lock; py update ;;
  run)    check_lock; py run ;;
  *)      usage; [ "${1:-}" = "-h" ] && exit 0 || exit 1 ;;
esac
