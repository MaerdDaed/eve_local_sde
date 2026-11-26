# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""
结合停靠规则，从 SDE 中提取所有支持停靠的建筑信息，合并成 output/docking_structures.jsonl。

建筑范围 = 停靠矩阵全部行（读取 4.1 生成的 docking_rules.jsonl 的 dock_rule 记录）：
  - 全部已发布玩家建筑（categoryID=65，含变体，如"德拉库斯"铁壁 / "天空之境"星城，
    由 4.1 按 (groupID, rigSize) 继承原型矩阵自动生成）
  - NPC 空间站（output/npcStationTypes.jsonl 中全部 typeID，44 个）

每条记录 = SDE 建筑静态信息（typeID/名称/尺寸/组/分类）+ 该建筑的停靠行为
（对 4 类 XL 舰船的 dock_state 映射，取自 4.1 生成的 docking_rules.jsonl）。

建筑清单不再硬编码：玩家建筑来自 docking_rules.jsonl，其名称/分组/分类/发布状态
由 types/groups/categories 关联查询补全。

键为 structure_key：
  - 玩家建筑 → typeID(int)
  - NPC 站    → typeID(int)

用法:
    python 4.2.extract_docking_structures.py

退出码:
    0  生成成功
    1  缺少 docking_rules.jsonl（需先运行 4.1）、types.jsonl 或 npcStationTypes.jsonl
"""

import io
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
JSONL_DIR = os.path.join(BASE, "jsonl")
OUT_DIR = os.path.join(BASE, "output")

SRC_RULES = os.path.join(OUT_DIR, "docking_rules.jsonl")
SRC_TYPES = os.path.join(JSONL_DIR, "types.jsonl")
SRC_GROUPS = os.path.join(JSONL_DIR, "groups.jsonl")
SRC_NPC_TYPES = os.path.join(OUT_DIR, "npcStationTypes.jsonl")
DST_STRUCTURES = os.path.join(OUT_DIR, "docking_structures.jsonl")

XL_CLASS_ORDER = ("freight_jf", "rorqual", "capital_combat", "supercapital")


def load_dock_rules():
    """读取 docking_rules.jsonl 的 dock_rule 记录。

    返回 {structure_key: {structure_type, name, size, docking}}，
    其中 NPC 站的 structure_key 用字符串 'npc'，玩家建筑用 typeID(int)。
    """
    if not os.path.exists(SRC_RULES):
        return None
    rules = {}
    with io.open(SRC_RULES, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            if obj.get("kind") != "dock_rule":
                continue
            docking = {
                k: obj.get("docking", {}).get(k) for k in XL_CLASS_ORDER
            }
            key = "npc" if obj.get("structure_type") == "npc_station" else obj["structure_id"]
            rules[key] = {
                "structure_type": obj.get("structure_type"),
                "name": obj.get("structure_name"),
                "name_en": obj.get("name_en"),
                "size": obj.get("size"),
                "docking": docking,
            }
    return rules


def load_groups():
    """读取 groups.jsonl，建立 {groupID: {categoryID, groupNameID}}。"""
    if not os.path.exists(SRC_GROUPS):
        return {}
    g = {}
    with io.open(SRC_GROUPS, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            v = obj.get("value", {})
            g[v["groupID"]] = {
                "categoryID": v.get("categoryID"),
                "groupNameID": v.get("groupNameID"),
            }
    return g


def load_categories():
    """读取 categories.jsonl，建立 {categoryID: categoryNameID}。"""
    path = os.path.join(JSONL_DIR, "categories.jsonl")
    if not os.path.exists(path):
        return {}
    c = {}
    with io.open(path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            v = obj.get("value", {})
            c[v["categoryID"]] = v.get("categoryNameID")
    return c


def load_type_info():
    """读取 types.jsonl，建立 {typeID: {name, groupID, published}}。"""
    t = {}
    with io.open(SRC_TYPES, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            v = obj.get("value", {})
            t[v["typeID"]] = {
                "name": v.get("typeNameID"),
                "groupID": v.get("groupID"),
                "published": v.get("published"),
            }
    return t


def extract_npc_station_ids():
    """读取 npcStationTypes.jsonl 全部 typeID（按 key）。"""
    ids = []
    if not os.path.exists(SRC_NPC_TYPES):
        return None
    with io.open(SRC_NPC_TYPES, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            ids.append(json.loads(raw)["key"])
    return sorted(set(ids))


def main():
    for p in (SRC_RULES, SRC_TYPES, SRC_NPC_TYPES):
        if not os.path.exists(p):
            print("missing: {}".format(p))
            print("Run the prerequisite scripts first (4.1, 2.2/3.3).")
            return 1

    if not os.path.exists(OUT_DIR):
        os.makedirs(OUT_DIR)

    rules = load_dock_rules()
    groups = load_groups()
    categories = load_categories()
    types = load_type_info()
    npc_ids = extract_npc_station_ids()

    records = []

    # 玩家建筑：来自 docking_rules.jsonl 的 upwell 记录（含变体）
    for key, meta in rules.items():
        if meta["structure_type"] != "upwell":
            continue
        tid = key
        ti = types.get(tid, {})
        gid = ti.get("groupID")
        gin = groups.get(gid, {})
        cat = categories.get(gin.get("categoryID"))
        records.append({
            "structure_key": tid,
            "structure_type": "upwell",
            "typeID": tid,
            "name": meta["name"] or ti.get("name"),
            "name_en": meta["name_en"],
            "size": meta["size"],
            "category": "玩家建筑",
            "groupID": gid,
            "groupName": gin.get("groupNameID"),
            "categoryID": gin.get("categoryID"),
            "categoryName": cat,
            "published": ti.get("published"),
            "docking": dict(meta["docking"]),
        })

    # NPC 空间站
    npc_meta = rules.get("npc", {})
    for type_id in npc_ids:
        ti = types.get(type_id, {})
        gid = ti.get("groupID")
        gin = groups.get(gid, {})
        cat = categories.get(gin.get("categoryID"))
        records.append({
            "structure_key": type_id,
            "structure_type": "npc_station",
            "typeID": type_id,
            "name": ti.get("name"),
            "size": None,
            "category": "NPC 空间站",
            "groupID": gid,
            "groupName": gin.get("groupNameID"),
            "categoryID": gin.get("categoryID"),
            "categoryName": cat,
            "published": ti.get("published"),
            "docking": dict(npc_meta.get("docking", {})),
        })

    # 排序：先 NPC 站（按 typeID），再玩家建筑（按 typeID）
    records.sort(key=lambda r: (r["structure_type"] != "npc_station", r["typeID"]))

    with io.open(DST_STRUCTURES, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")

    upwell = sum(1 for r in records if r["structure_type"] == "upwell")
    print("  -> {} ({} lines: {} upwell + {} npc)".format(
        DST_STRUCTURES, len(records), upwell, len(records) - upwell))
    return 0


if __name__ == "__main__":
    sys.exit(main())
