#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ola-app SDE 数据包：自检、生成 manifest.json、组包。

输入是已经凑齐 13 个 jsonl 文件的目录，输出三个发布资产：
    ola-app-jsonl-cn<build>.tar.gz          包内为 manifest.json + jsonl/（13 个文件）
    ola-app-jsonl-cn<build>.tar.gz.sha256   sha256sum -c 格式的整包摘要
    manifest.json                           与包内相同，单独放一份供不下载整包时查看

自检共五项，任一项失败即以退出码 1 结束，不产出任何文件：
    可解析        每个文件逐行可解析为 JSON 对象
    文件齐全      13 个文件全部存在，且没有清单之外的 jsonl
    引用完整性    星系的星域、星座，以及星门边的两个端点都能找到
    星门一致      每个星系的星门数等于它的出边数
    邻接交叉校验  jumps.static 的星系间记录全部包含在 starmapcache 的邻接表里
                  （gen_map_from_cn.py 会把缺失的对并进输出，这里按并集前的邻接表校验，
                  出现缺失说明邻接表结构变了，需要人工确认后才能发布）

用法:
    python3 build_package.py --jsonl-dir DIR --client-root EVESharedCache根目录 \\
        --build 3736091 --toolchain <提交哈希> --out-dir DIR
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import io
import json
import os
import pickle
import sys
import tarfile

import gen_map_from_cn

# 按生成步骤分组（见仓库 README「生成步骤」）
FILES = (
    "items_output.jsonl",
    "blueprints_output.jsonl",
    "ships_output.jsonl",
    "categories.jsonl",
    "races.jsonl",
    "factions.jsonl",
    "mapSolarSystems.jsonl",
    "mapConstellations.jsonl",
    "mapRegions.jsonl",
    "mapSolarSystemJumps.jsonl",
    "docking_rules.jsonl",
    "docking_structures.jsonl",
    "jump_fatigue_ships.jsonl",
)


class CheckError(Exception):
    """自检失败。"""


def read_jsonl(name: str, path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for number, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise CheckError(f"可解析: {name} 第 {number} 行不是合法 JSON（{exc}）") from exc
            if not isinstance(row, dict):
                raise CheckError(f"可解析: {name} 第 {number} 行不是 JSON 对象")
            rows.append(row)
    return rows


def check_files(jsonl_dir: str) -> dict[str, list[dict]]:
    present = sorted(name for name in os.listdir(jsonl_dir) if name.endswith(".jsonl"))
    missing = [name for name in FILES if name not in present]
    unexpected = [name for name in present if name not in FILES]
    if missing or unexpected:
        raise CheckError(
            f"文件齐全: 缺少 {missing}，多出 {unexpected}")
    return {name: read_jsonl(name, os.path.join(jsonl_dir, name)) for name in FILES}


def check_references(tables: dict[str, list[dict]]) -> None:
    systems = tables["mapSolarSystems.jsonl"]
    known = {
        "constellationID": {row["_key"] for row in tables["mapConstellations.jsonl"]},
        "regionID": {row["_key"] for row in tables["mapRegions.jsonl"]},
    }
    system_ids = {row["_key"] for row in systems}
    bad = []
    for row in systems:
        for field, ids in known.items():
            if row.get(field) not in ids:
                bad.append(f"星系 {row.get('_key')} 的 {field}={row.get(field)} 不存在")
    for row in tables["mapSolarSystemJumps.jsonl"]:
        for field in ("fromSolarSystemId", "toSolarSystemId"):
            if row.get(field) not in system_ids:
                bad.append(f"星门边的 {field}={row.get(field)} 不是已导出的星系")
    if bad:
        raise CheckError(f"引用完整性: {len(bad)} 处，例如 " + "；".join(bad[:3]))


def check_stargates(tables: dict[str, list[dict]]) -> None:
    out_edges = collections.Counter(
        row["fromSolarSystemId"] for row in tables["mapSolarSystemJumps.jsonl"])
    bad = []
    for row in tables["mapSolarSystems.jsonl"]:
        gates = len(row.get("stargateIDs") or [])
        if gates != out_edges.get(row["_key"], 0):
            bad.append(f"星系 {row['_key']} 星门数 {gates} ≠ 出边数 {out_edges.get(row['_key'], 0)}")
    if bad:
        raise CheckError(f"星门一致: {len(bad)} 个星系不一致，例如 " + "；".join(bad[:3]))


def check_adjacency(client_root: str) -> tuple[int, int]:
    index = gen_map_from_cn.load_index(client_root)
    jumps = gen_map_from_cn.parse_jumps(
        gen_map_from_cn.res_path(client_root, index, "res:/staticdata/jumps.static"))
    jumps_solar = {(min(a, b), max(a, b)) for _j, _g, a, b, kind in jumps if kind == 0}
    cache_path = gen_map_from_cn.res_path(
        client_root, index, "res:/staticdata/starmapcache.pickle")
    with open(cache_path, "rb") as fh:
        cache = pickle.load(fh, encoding="latin1")
    pairs = set()
    for system_id, entry in cache.get("solarSystems", {}).items():
        for neighbour in entry.get("neighbours") or []:
            pairs.add((min(system_id, neighbour), max(system_id, neighbour)))
    missing = jumps_solar - pairs
    if missing:
        raise CheckError(
            f"邻接交叉校验: jumps.static 有 {len(missing)} 对星系间记录不在邻接表里，"
            f"例如 {sorted(missing)[:3]}")
    return len(jumps_solar), len(pairs)


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="ola-app SDE 数据包：自检、manifest、组包")
    parser.add_argument("--jsonl-dir", required=True, help="已凑齐 13 个 jsonl 文件的目录")
    parser.add_argument("--client-root", required=True, help="EVESharedCache 根目录")
    parser.add_argument("--build", required=True, help="国服客户端 build 号")
    parser.add_argument("--toolchain", required=True, help="工具链提交哈希")
    parser.add_argument("--out-dir", required=True, help="发布资产的输出目录")
    args = parser.parse_args()

    tables = check_files(args.jsonl_dir)
    check_references(tables)
    check_stargates(tables)
    jumps_count, pairs_count = check_adjacency(args.client_root)
    for name in FILES:
        print(f"  {len(tables[name]):>7}  {name}")
    print(f"自检通过: 13 个文件可解析且齐全，引用完整，星门与出边一致，"
          f"jumps.static solar={jumps_count} ⊆ 邻接表 pairs={pairs_count}")

    manifest = {
        "clientBuild": args.build,
        "generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "toolchain": f"eve_local_sde@{args.toolchain}",
        "files": {
            f"jsonl/{name}": {
                "sha256": sha256_of(os.path.join(args.jsonl_dir, name)),
                "lines": len(tables[name]),
            }
            for name in FILES
        },
    }
    data = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    os.makedirs(args.out_dir, exist_ok=True)
    package = os.path.join(args.out_dir, f"ola-app-jsonl-cn{args.build}.tar.gz")
    with tarfile.open(package, "w:gz") as tar:
        info = tarfile.TarInfo("manifest.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
        for name in FILES:
            tar.add(os.path.join(args.jsonl_dir, name), arcname=f"jsonl/{name}")

    digest = sha256_of(package)
    with open(package + ".sha256", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{digest}  {os.path.basename(package)}\n")
    with open(os.path.join(args.out_dir, "manifest.json"), "wb") as fh:
        fh.write(data)
    print(f"已组包: {package} sha256={digest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckError as exc:
        print(f"自检失败，不发布: {exc}", file=sys.stderr)
        raise SystemExit(1)
