#!/usr/bin/env bash
# ola-app SDE jsonl 流水线入口。开发机 cron 在 11:00–11:55 每 5 分钟调用一次：
# CDN 上出现新的国服客户端 build 时，更新客户端缓存、生成 13 个数据文件、自检、组包并发布 Release。
#
# 必需的环境变量（与本机相关的路径，不写进仓库）：
#   EVE_CLIENT_CACHE   EVESharedCache 根目录（含 ResFiles/ 与 serenity/），工具链工作目录在它下面
#   EVE_UPDATE_CLIENT  update_cn_client.py 的路径（读 CDN 最新 build、增量更新客户端缓存）
# 可选：
#   EVE_SDE_RELEASE_REPO  发布 Release 的仓库，默认 MaerdDaed/eve_local_sde
#   EVE_WINE_IMAGE        跑 1.execute_loaders.py 的 Wine 镜像，默认 evejs-wine-sde:1
#   EVE_SDE_WORKSPACE     工具链工作目录，默认 $EVE_CLIENT_CACHE/workspace
#   EVE_SDE_LOCK          文件锁路径，默认 /tmp/eve_local_sde.lock
#   EVE_SDE_DRY_RUN=1     走完生成、自检、组包，停在发布之前（手工验证用），产物目录保留并打印
#
# 客户端缓存的更新下载加生成可能超过 5 分钟的检查间隔：用文件锁保证两次运行不叠在一起。
# 任何一步失败都会直接退出（退出码非 0），不会发布半成品。
set -euo pipefail

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
die() { log "失败: $*"; exit 1; }
need() { [ -n "${!1:-}" ] || die "未设置环境变量 $1（见脚本头部说明）"; }

need EVE_CLIENT_CACHE
need EVE_UPDATE_CLIENT

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SLUG="${EVE_SDE_RELEASE_REPO:-MaerdDaed/eve_local_sde}"
IMAGE="${EVE_WINE_IMAGE:-evejs-wine-sde:1}"
CACHE="${EVE_CLIENT_CACHE}"
WORKSPACE="${EVE_SDE_WORKSPACE:-$CACHE/workspace}"
LOCK="${EVE_SDE_LOCK:-/tmp/eve_local_sde.lock}"
DRY_RUN="${EVE_SDE_DRY_RUN:-0}"

exec 9>"$LOCK"
if ! flock -n 9; then
  log "上一次运行尚未结束，本次跳过"
  exit 0
fi

WORK="$(mktemp -d /tmp/eve_local_sde-run.XXXXXX)"
cleanup() {
  if [ "$KEEP" = "1" ]; then log "产物保留在 $WORK"; else rm -rf "$WORK"; fi
}
KEEP=0
trap cleanup EXIT
trap 'log "失败（见上方输出），不发布"' ERR

in_workspace() { (cd "$WORKSPACE" && "$@"); }

TOOLCHAIN="$(git -C "$REPO_DIR" rev-parse HEAD)"

log "检查 CDN 上的最新 build"
python3 "$EVE_UPDATE_CLIENT" --dry-run --cache "$CACHE" > "$WORK/plan.txt" 2>&1 || {
  cat "$WORK/plan.txt"
  die "读取 CDN build 失败"
}
cat "$WORK/plan.txt"
BUILD="$(sed -n 's/^CDN build (serenity) = \([0-9]\{1,\}\)$/\1/p' "$WORK/plan.txt")"
[ -n "$BUILD" ] || die "没能从 update_cn_client.py 的输出里解析出 build 号"
log "CDN 最新 build = $BUILD，工具链 = $TOOLCHAIN"

EXISTING="$(gh release view "$BUILD" --repo "$SLUG" --json tagName --jq .tagName 2>&1)" && {
  log "build $BUILD 已有 Release，本次无事可做"
  exit 0
}
case "$EXISTING" in
  *"release not found"*) ;;
  *) die "查询 Release 失败: $EXISTING" ;;
esac

log "更新客户端缓存到 build $BUILD"
python3 "$EVE_UPDATE_CLIENT" --cache "$CACHE"

log "同步工具链脚本到 $WORKSPACE"
mkdir -p "$WORKSPACE/output"
cp "$REPO_DIR"/workspace/*.py "$WORKSPACE"/
cp "$REPO_DIR"/ola-app/gen_map_from_cn.py "$REPO_DIR"/ola-app/gen_jump_fatigue_ships.py "$WORKSPACE"/

log "步骤 1/6 准备 workspace"
# 上一版 jsonl/ → jsonl.bak/ 的备份由 1.execute_loaders.py 自己做，用于生成 changeLog.md
in_workspace python3 0.prepare_workspace.py

log "步骤 2/6 解析 FSD 表（Wine + Python 2.7）"
docker run --rm --network none -v "$WORKSPACE:/work" -w /work "$IMAGE" \
  /opt/py27/python.exe Z:/work/1.execute_loaders.py zh

log "步骤 3/6 提取物品、蓝图、舰船"
for script in 2.1.extract_blueprints.py 2.2.extract_items.py 2.3.extract_ships.py \
    2.4.extract_categories.py 2.6.extract_race_faction.py; do
  in_workspace python3 "$script"
done

log "步骤 4/6 解析星图"
python3 "$WORKSPACE/gen_map_from_cn.py" --client-root "$CACHE" --out-dir "$WORK/cnmap"

log "步骤 5/6 停靠规则"
# npcStations 先换成国服版（星图脚本的产物），3.3 才不会拿别的服务器的空间站 typeID 去筛
cp "$WORK/cnmap/npcStations.jsonl" "$WORKSPACE/output/npcStations.jsonl"
for script in 3.3.extract_station_types.py 4.1.generate_docking_rules.py \
    4.2.extract_docking_structures.py; do
  in_workspace python3 "$script"
done

log "步骤 6/6 跳跃疲劳系数"
in_workspace python3 gen_jump_fatigue_ships.py output/ships_output.jsonl output/jump_fatigue_ships.jsonl

log "组装 13 个数据文件"
mkdir "$WORK/jsonl"
for name in items_output blueprints_output ships_output categories races factions \
    docking_rules docking_structures jump_fatigue_ships; do
  cp "$WORKSPACE/output/$name.jsonl" "$WORK/jsonl/"
done
for name in mapSolarSystems mapConstellations mapRegions mapSolarSystemJumps; do
  cp "$WORK/cnmap/$name.jsonl" "$WORK/jsonl/"
done

log "自检、生成 manifest、组包"
python3 "$REPO_DIR/ola-app/build_package.py" \
  --jsonl-dir "$WORK/jsonl" --client-root "$CACHE" \
  --build "$BUILD" --toolchain "$TOOLCHAIN" --out-dir "$WORK/dist"

if [ "$DRY_RUN" = "1" ]; then
  KEEP=1
  log "EVE_SDE_DRY_RUN=1：停在发布之前"
else
  log "发布 Release $BUILD"
  python3 "$REPO_DIR/ola-app/publish_release.py" \
    --build "$BUILD" --assets-dir "$WORK/dist" --repo "$SLUG"
fi
log "完成"
