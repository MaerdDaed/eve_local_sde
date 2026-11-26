#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只用晨曦（Serenity）客户端数据生成 ola-app 需要的星图 jsonl。

不读取任何 CCP/TQ（宁静）数据源：星图、星门、空间站全部来自国服客户端缓存。

输入（全部在 EVESharedCache 内）：
  serenity/resfileindex.txt                        资源索引（res:/ -> 哈希路径）
  ResFiles/<hashed>/staticdata/systems.static      星系（含 nameID / 安全等级 / 坐标）
  ResFiles/<hashed>/staticdata/constellations.static
  ResFiles/<hashed>/staticdata/regions.static
  ResFiles/<hashed>/staticdata/starmapcache.pickle 邻接表、factionID、sunTypeID、planetItemIDs
  ResFiles/<hashed>/localizationfsd/localization_fsd_<lang>.pickle   8 语言名称
  serenity/bin64/staticdata/mapObjects.db          celestials（星门/恒星）+ npcStations

输出（ola-app jsonl 形状）：
  mapSolarSystems.jsonl / mapConstellations.jsonl / mapRegions.jsonl
  mapSolarSystemJumps.jsonl / npcStations.jsonl

字段取舍见 README / CHANGES：TQ SDE 独有的展示字段
（border/hub/international/luminosity/position2D/regional）国服客户端不提供，故不输出；
description / securityClass / wormholeClassID 位于 .static 的可变段，本工具未解析，
需要时后续补（ola-app 侧无消费方）。

用法：
  python3 gen_map_from_cn.py --client-root <EVESharedCache> --out-dir out/
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sqlite3
import struct
import sys

LANGS = [("de", "de"), ("en", "en-us"), ("es", "es"), ("fr", "fr"),
         ("ja", "ja"), ("ko", "ko"), ("ru", "ru"), ("zh", "zh")]

SYSTEM_FIXED = struct.Struct("<IfIII3df")   # id, security, constellation, region, nameID, xyz, pseudo
CONSTELLATION_FIXED = struct.Struct("<III3d")  # id, region, nameID, xyz
REGION_FIXED = struct.Struct("<II3dI")      # id, nameID, xyz, nebulaID
JUMP_FIXED = struct.Struct("<IIIIB")        # jumpID, stargateID, from, to, jumpType
JUMP_STRIDE = 65                            # 记录固定 65 字节（schema fixedItemSize）


def load_index(root: str) -> dict[str, str]:
    path = os.path.join(root, "serenity", "resfileindex.txt")
    index: dict[str, str] = {}
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            parts = line.rstrip("\n").split(",")
            if len(parts) >= 4 and parts[0].startswith("res:/"):
                index[parts[0]] = parts[1]
    return index


def res_path(root: str, index: dict[str, str], vpath: str) -> str:
    if vpath not in index:
        raise SystemExit(f"索引里找不到 {vpath}（客户端缓存不完整？）")
    return os.path.join(root, "ResFiles", index[vpath].replace("/", os.sep))


def load_localisation(root: str, index: dict[str, str]) -> dict[str, dict[int, str]]:
    tables: dict[str, dict[int, str]] = {}
    for key, suffix in LANGS:
        path = res_path(root, index, f"res:/localizationfsd/localization_fsd_{suffix}.pickle")
        with open(path, "rb") as fh:
            obj = pickle.load(fh, encoding="latin1")
        raw = obj[1] if isinstance(obj, tuple) else obj
        tables[key] = {mid: (val[0] if isinstance(val, (tuple, list)) else val)
                       for mid, val in raw.items()}
    return tables


def decode_static(path: str, fixed: struct.Struct) -> dict[int, tuple]:
    """解 footer 索引的 .static：footer 每项 (key, offset)，记录体自 4 字节头后开始。"""
    with open(path, "rb") as fh:
        data = fh.read()
    footer_size = struct.unpack_from("<I", data, len(data) - 4)[0]
    footer_start = len(data) - footer_size
    count = (footer_size - 4) // 8
    entries = [struct.unpack_from("<II", data, footer_start + i * 8) for i in range(count)]
    entries.sort(key=lambda item: item[1])
    records: dict[int, tuple] = {}
    for i, (key, offset) in enumerate(entries):
        end = entries[i + 1][1] if i + 1 < len(entries) else footer_start - 4
        raw = data[4 + offset:4 + end]
        records[key] = fixed.unpack_from(raw, 0)
    return records


def parse_jumps(path: str) -> list[tuple[int, int, int, int]]:
    with open(path, "rb") as fh:
        data = fh.read()
    count = struct.unpack_from("<I", data, 0)[0]
    expected = 4 + count * JUMP_STRIDE
    if len(data) < expected:
        raise SystemExit(f"jumps.static 长度异常: {len(data)} < {expected}")
    out = []
    for i in range(count):
        jump_id, gate_id, src, dst, kind = JUMP_FIXED.unpack_from(data, 4 + i * JUMP_STRIDE)
        out.append((jump_id, gate_id, src, dst, kind))
    return out


def load_map_db(path: str):
    con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    try:
        celestials = con.execute(
            "select celestialID, solarSystemID, typeID, groupID, radius from celestials"
        ).fetchall()
        stations = con.execute(
            "select stationID, solarSystemID, ownerID, typeID, x, y, z, orbitID, orbitIndex,"
            " celestialIndex, operationID, reprocessingEfficiency, reprocessingStationsTake,"
            " reprocessingHangarFlag, isConquerable, useOperationName from npcStations"
        ).fetchall()
    finally:
        con.close()
    return celestials, stations


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-root", required=True, help="EVESharedCache 根目录")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    root = args.client_root
    index = load_index(root)
    names = load_localisation(root, index)
    systems = decode_static(res_path(root, index, "res:/staticdata/systems.static"), SYSTEM_FIXED)
    constellations = decode_static(res_path(root, index, "res:/staticdata/constellations.static"),
                                  CONSTELLATION_FIXED)
    regions = decode_static(res_path(root, index, "res:/staticdata/regions.static"), REGION_FIXED)
    jumps = parse_jumps(res_path(root, index, "res:/staticdata/jumps.static"))
    with open(res_path(root, index, "res:/staticdata/starmapcache.pickle"), "rb") as fh:
        cache = pickle.load(fh, encoding="latin1")
    celestials, stations = load_map_db(
        os.path.join(root, "serenity", "bin64", "staticdata", "mapObjects.db"))

    os.makedirs(args.out_dir, exist_ok=True)

    def loc(name_id: int) -> dict[str, str]:
        out = {}
        for key, _suffix in LANGS:
            value = names[key].get(name_id)
            out[key] = value if value is not None else ""
        return out

    gates_by_system: dict[int, list[int]] = {}
    stars: dict[int, tuple[int, float]] = {}
    for cid, sid, type_id, group_id, radius in celestials:
        if group_id == 10:
            gates_by_system.setdefault(sid, []).append(cid)
        elif group_id == 6:
            stars.setdefault(sid, (cid, radius))

    cache_systems = cache.get("solarSystems", {})
    rows = []
    for system_id in sorted(systems):
        sid, security, const_id, region_id, name_id, x, y, z, _pseudo = systems[system_id]
        entry = cache_systems.get(system_id, {})
        star_id, star_radius = stars.get(system_id, (0, 0.0))
        rows.append({
            "_key": system_id,
            "name": loc(name_id),
            "constellationID": const_id,
            "regionID": region_id,
            "position": {"x": x, "y": y, "z": z},
            "securityStatus": security,
            "factionID": entry.get("factionID"),
            "sunTypeID": entry.get("sunTypeID"),
            "starID": star_id,
            "radius": star_radius,
            "planetIDs": sorted(entry.get("planetItemIDs") or []),
            "stargateIDs": sorted(gates_by_system.get(system_id, [])),
        })
    write(os.path.join(args.out_dir, "mapSolarSystems.jsonl"), rows)

    cache_constellations = cache.get("constellations", {})
    rows = []
    for const_id in sorted(constellations):
        cid, region_id, name_id, x, y, z = constellations[const_id]
        entry = cache_constellations.get(const_id, {})
        rows.append({
            "_key": const_id,
            "name": loc(name_id),
            "regionID": region_id,
            "position": {"x": x, "y": y, "z": z},
            "solarSystemIDs": sorted(entry.get("solarSystemIDs") or []),
            "factionID": entry.get("factionID"),
        })
    write(os.path.join(args.out_dir, "mapConstellations.jsonl"), rows)

    cache_regions = cache.get("regions", {})
    rows = []
    for region_id in sorted(regions):
        rid, name_id, x, y, z, nebula_id = regions[region_id]
        entry = cache_regions.get(region_id, {})
        rows.append({
            "_key": region_id,
            "name": loc(name_id),
            "position": {"x": x, "y": y, "z": z},
            "nebulaID": nebula_id,
            "constellationIDs": sorted(entry.get("constellationIDs") or []),
            "factionID": entry.get("factionID"),
        })
    write(os.path.join(args.out_dir, "mapRegions.jsonl"), rows)

    # 星门有向边：优先用 starmapcache 的邻接表（双向已对称，覆盖完整），
    # 用 jumps.static 的 solar-system 记录做交叉校验。
    pairs = set()
    for system_id, entry in cache_systems.items():
        for neighbour in entry.get("neighbours") or []:
            pairs.add((min(system_id, neighbour), max(system_id, neighbour)))
    jumps_solar = {(min(a, b), max(a, b)) for _j, _g, a, b, kind in jumps if kind == 0}
    missing = jumps_solar - pairs
    if missing:
        print(f"!! jumps.static 有 {len(missing)} 对边不在邻接表里，已并入", file=sys.stderr)
        pairs |= missing

    directed = set()
    for a, b in pairs:
        directed.add((a, b))
        directed.add((b, a))
    edges = [{"fromSolarSystemId": a, "toSolarSystemId": b} for a, b in sorted(directed)]
    write(os.path.join(args.out_dir, "mapSolarSystemJumps.jsonl"), edges)

    station_rows = []
    for row in stations:
        station_id, system_id, owner, type_id, x, y, z, orbit_id, orbit_index, \
            celestial_index, operation_id, repro_eff, repro_take, repro_flag, conquerable, use_op = row
        station_rows.append({
            "_key": station_id,
            "solarSystemID": system_id,
            "ownerID": owner,
            "typeID": type_id,
            "position": {"x": x, "y": y, "z": z},
            "orbitID": orbit_id,
            "orbitIndex": orbit_index,
            "celestialIndex": celestial_index,
            "operationID": operation_id,
            "reprocessingEfficiency": repro_eff,
            "reprocessingStationsTake": repro_take,
            "reprocessingHangarFlag": repro_flag,
            "isConquerable": bool(conquerable),
            "useOperationName": bool(use_op),
        })
    write(os.path.join(args.out_dir, "npcStations.jsonl"), station_rows)

    print(f"systems={len(systems)} constellations={len(constellations)} regions={len(regions)}")
    print(f"gate pairs={len(pairs)} directed edges={len(directed)} (jumps.static solar={len(jumps_solar)})")
    print(f"npcStations={len(station_rows)}")
    return 0


def write(path: str, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())