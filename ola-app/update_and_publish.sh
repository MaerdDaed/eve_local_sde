#!/usr/bin/env bash
# ola-app SDE jsonl 生成流水线入口。只负责「CDN 上出现新的国服客户端 build 时，生成数据并放在约定的地方」；
# 什么时候调用、产物怎么上传到 dev/prd，由另外的流程负责，不在这个脚本里。
#
# 每次运行：
#   1. 读 CDN 上的最新 build。
#   2. 生成：更新客户端缓存、生成 13 个数据文件、自检、组包。设了 EVE_SDE_OUT_DIR 时，产物目录里已有这个 build
#      就不重新生成；新生成的产物放进产物目录，并把 latest 换过去（布局见 README「交接给上传方」）。
#   3. 留档：把产物发布成 GitHub Release（备份）。该 build 的 Release 已齐全就跳过；设了 EVE_SDE_OUT_DIR 时，
#      即使这一轮没有生成，也会把上一轮没发成的补发出去，不必重新生成。
#
# 必需的环境变量（与本机相关的路径，不写进仓库）：
#   EVE_CLIENT_CACHE   EVESharedCache 根目录（含 ResFiles/ 与 serenity/），工具链工作目录在它下面
#   EVE_UPDATE_CLIENT  update_cn_client.py 的路径（读 CDN 最新 build、增量更新客户端缓存）
# 可选：
#   EVE_SDE_OUT_DIR         产物目录，交接给上传流程用。不设时产物不保留：以「GitHub 上的 Release 是否齐全」
#                           判断是否已生成，生成后立即发布
#   EVE_SDE_RELEASE_REPO    留档仓库，默认 MaerdDaed/eve_local_sde
#   EVE_SDE_PUBLISH_RELEASE 设为 0 时不发布 GitHub Release（只生成）
#   EVE_WINE_IMAGE          跑 1.execute_loaders.py 的 Wine 镜像，默认 evejs-wine-sde:1
#   EVE_SDE_WORKSPACE       工具链工作目录，默认 $EVE_CLIENT_CACHE/workspace
#   EVE_SDE_LOCK            文件锁路径，默认 /tmp/eve_local_sde.lock
#   EVE_SDE_DRY_RUN=1       走完生成、自检、组包后停住：不发布，也不动产物目录（产物留在临时目录并打印路径）
#
# 退出码：0 表示成功或本次无事可做，非 0 表示失败。生成不依赖 GitHub 凭据，拿不到凭据时只影响留档。
# 客户端缓存的更新下载加生成可能超过调用间隔：用文件锁保证两次运行不叠在一起。
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
OUT_DIR="${EVE_SDE_OUT_DIR:-}"
PUBLISH="${EVE_SDE_PUBLISH_RELEASE:-1}"
DRY_RUN="${EVE_SDE_DRY_RUN:-0}"

if [ -n "$OUT_DIR" ]; then
  # 产物目录归这个脚本管理：里面的旧版本会被删掉。只接受绝对路径（定时任务的当前目录不定）；
  # 规范化路径（去掉 ..、解析符号链接）再判断：不能是一个大目录，也不能把客户端缓存、工作目录或仓库包含在里面
  case "$OUT_DIR" in
    /*) ;;
    *) die "EVE_SDE_OUT_DIR 必须是绝对路径: $OUT_DIR" ;;
  esac
  OUT_DIR="$(realpath -m -- "$OUT_DIR")"
  case "$OUT_DIR" in
    /*/*) ;;
    *) die "EVE_SDE_OUT_DIR 必须是至少两级的绝对路径: $OUT_DIR" ;;
  esac
  for kept in "$CACHE" "$WORKSPACE" "$REPO_DIR"; do
    kept="$(realpath -m -- "$kept")"
    if [ "$kept" = "$OUT_DIR" ] || [[ "$kept/" == "$OUT_DIR"/* ]]; then
      die "EVE_SDE_OUT_DIR 不能是 $kept，也不能把它包含在里面"
    fi
  done
  # 只接管空目录，或本脚本管理过的目录（有标记文件）。指到一个已有内容的别的目录上，多半是配错了
  if [ -e "$OUT_DIR" ] && [ -n "$(ls -A "$OUT_DIR" 2>/dev/null)" ] && [ ! -e "$OUT_DIR/.eve-sde-outbox" ]; then
    die "EVE_SDE_OUT_DIR 不是空目录，也不是本脚本管理过的产物目录: $OUT_DIR"
  fi
fi

exec 9>"$LOCK"
if ! flock -n 9; then
  log "上一次运行尚未结束，本次跳过"
  exit 0
fi

WORK="$(mktemp -d /tmp/eve_local_sde-run.XXXXXX)"
KEEP=0
STAGE=""
cleanup() {
  if [ "$KEEP" = "1" ]; then
    [[ "${DIST:-}" == "$WORK"/* ]] && log "产物保留在 $DIST"
  else
    rm -rf "$WORK"
  fi
  [ -z "${STAGE:-}" ] || rm -rf "$STAGE"
}
trap cleanup EXIT
trap 'log "本轮失败（见上方输出），退出码 $?"' ERR

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

PACKAGE="ola-app-jsonl-cn$BUILD.tar.gz"
EXPECTED="manifest.json,$PACKAGE,$PACKAGE.sha256"

# Release 是否齐全。创建 Release 与上传资产是两步，上传中途失败会留下一个资产不全的 Release。
release_state() {
  local assets status
  assets="$(timeout 60 gh release view "$BUILD" --repo "$SLUG" \
    --json assets --jq '[.assets[].name] | sort | join(",")' 2>&1)" && status=0 || status=$?
  if [ "$status" = "0" ]; then
    if [ "$assets" = "$EXPECTED" ]; then RELEASE_STATE=complete; else RELEASE_STATE=partial; fi
  elif [[ "$assets" == *"release not found"* ]]; then
    RELEASE_STATE=missing
  else
    die "查询 Release 失败: $assets"
  fi
}

# 这一轮的产物：已经有了就直接用，没有才生成。DIST 为空表示还没生成。
DIST=""
if [ -n "$OUT_DIR" ]; then
  if [ -s "$OUT_DIR/$BUILD/manifest.json" ] && [ -s "$OUT_DIR/$BUILD/$PACKAGE" ] \
      && [ -s "$OUT_DIR/$BUILD/$PACKAGE.sha256" ]; then
    log "build $BUILD 已生成过，在 $OUT_DIR/$BUILD，本次不重新生成"
    DIST="$OUT_DIR/$BUILD"
  fi
else
  release_state
  if [ "$RELEASE_STATE" = "complete" ]; then
    log "build $BUILD 已有 Release，本次无事可做"
    exit 0
  fi
  [ "$RELEASE_STATE" = "missing" ] || log "build $BUILD 的 Release 资产不全，重新生成并覆盖"
fi

if [ -z "$DIST" ]; then
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
  DIST="$WORK/dist"
fi

if [ "$DRY_RUN" = "1" ]; then
  KEEP=1
  log "EVE_SDE_DRY_RUN=1：停在这里，不发布、不动产物目录；产物在 $DIST"
  exit 0
fi

# 放进产物目录，交接给上传流程。先核对整包摘要，写进临时目录再改名，最后才把 latest 换过去，
# 所以上传方任何时候看到的 latest/ 都是完整的一版。产物目录里只留最新的一版。
hand_out() {
  (cd "$DIST" && sha256sum --check --quiet "$PACKAGE.sha256") || die "组包后的摘要核对不通过"
  mkdir -p "$OUT_DIR"
  # 标记文件表示这个目录由本脚本管理，之后的清理只认带标记的目录
  touch "$OUT_DIR/.eve-sde-outbox"
  rm -rf "$OUT_DIR/$BUILD"
  STAGE="$(mktemp -d "$OUT_DIR/.incoming.XXXXXX")"
  cp "$DIST/manifest.json" "$DIST/$PACKAGE" "$DIST/$PACKAGE.sha256" "$STAGE/"
  mv -T "$STAGE" "$OUT_DIR/$BUILD"
  STAGE=""
  chmod 755 "$OUT_DIR/$BUILD"   # mktemp 建的目录是 700；上传流程可能用别的账号来取
  rm -f "$OUT_DIR"/.latest.tmp.*   # 上一次在换链接前中断时留下的
  ln -s "$BUILD" "$OUT_DIR/.latest.tmp.$$"
  mv -T "$OUT_DIR/.latest.tmp.$$" "$OUT_DIR/latest"
  find "$OUT_DIR" -mindepth 1 -maxdepth 1 -type d \( -name '[0-9]*' -o -name '.incoming.*' \) \
    ! -name "$BUILD" -exec rm -rf {} +
  log "产物就绪: build=$BUILD，目录=$OUT_DIR/latest（上传方从这里取）"
}

if [ -n "$OUT_DIR" ] && [ "$DIST" = "$WORK/dist" ]; then
  hand_out
  DIST="$OUT_DIR/$BUILD"
fi

if [ "$PUBLISH" != "1" ]; then
  log "EVE_SDE_PUBLISH_RELEASE=$PUBLISH：不发布 GitHub Release"
  exit 0
fi

if [ -n "$OUT_DIR" ]; then
  release_state
  if [ "$RELEASE_STATE" = "complete" ]; then
    log "build $BUILD 已有 Release，留档无事可做"
    exit 0
  fi
  log "把 $DIST 发布成 Release $BUILD（留档）"
else
  log "发布 Release $BUILD"
fi
python3 "$REPO_DIR/ola-app/publish_release.py" \
  --build "$BUILD" --assets-dir "$DIST" --repo "$SLUG"
log "完成"
