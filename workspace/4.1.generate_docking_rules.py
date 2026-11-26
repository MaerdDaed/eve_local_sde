# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""
将从 EVE 舰船停靠规则整理出的「停靠规则」编码为 output/docking_rules.jsonl。

规则核心（见 dock_matrix 表）：
- 常规舰船（S/M/L 尺寸，即非旗舰/超旗级别的普通舰船）不受停靠矩阵限制，
  在矩阵列出的全部建筑（NPC 站 + 玩家建筑）中均可停靠 —— 用 default_policy 记录。
- 仅 XL 规格舰船（资本级/超级资本级）才受 dock_matrix 约束，分 4 类舰船。

建筑清单（含玩家建筑全部变体）不再硬编码，而是从 SDE 关联查询：
  types.jsonl (categoryID=65) → groups.jsonl (分组/分类) → typedogma.jsonl (规格/tether)。
停靠矩阵 DOCK_MATRIX 按「原型建筑 typeID」维护（社区整理的精确停靠知识，含
one_time_undock 等特例，无法从 category 推导）；变体通过 (groupID, rigSize)
关联到同组同规格的原型，自动继承其停靠矩阵。

产物（每行一个 JSON 对象，用 kind 区分记录类型）：
  kind="default_policy"  常规舰船全局可停靠不变式
  kind="ship_class"      XL 舰船分类定义（含该分类下全部舰船 typeID / group）
  kind="dock_rule"       按建筑一条，内嵌该建筑对 4 类 XL 舰船的 dock_state 映射

dock_state 枚举：
  dock                停靠
  tether              仅系泊（有停靠权限即可系泊，受护盾保护/被动维修，但不进站）
  one_time_undock     仅可建造出厂一次（在该建筑建造后起坞一次，之后无法再停靠）
  asset_safety_undock 仅资产安全出口可起飞一次（从资产安全取出后起坞一次）

用法:
    python 4.1.generate_docking_rules.py

退出码:
    0  生成成功
    1  缺少 ships_output.jsonl（需先运行 2.3）或 jsonl/types.jsonl
"""

import io
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
JSONL_DIR = os.path.join(BASE, "jsonl")
OUT_DIR = os.path.join(BASE, "output")
SRC_SHIPS = os.path.join(OUT_DIR, "ships_output.jsonl")
DST_RULES = os.path.join(OUT_DIR, "docking_rules.jsonl")

# 建筑规格(rigSize) → 尺寸标签
SIZE_LABEL = {2: "M", 3: "L", 4: "XL"}

# 原型建筑的英文名（命名知识，非 category 可推导；变体沿用其原型英文名）
PROTO_NAMES_EN = {
    35825: "Raitaru",  35826: "Azbel",  35827: "Sotiyo",     # 工程复合体
    35832: "Astrahus", 35833: "Fortizar", 35834: "Keepstar",  # 堡垒
    35835: "Athanor",  35836: "Tatara",                       # 精炼厂
}

# ── 舰船分类：group 名 → 停靠规则中的 class_id ─────────────────
# 对应停靠矩阵的 4 类 XL 舰船。
SHIP_GROUP_CLASS = {
    "货舰":        "freight_jf",      # Freighter
    "战略货舰":     "freight_jf",      # Jump Freighter（国服组名「战略货舰」）
    "旗舰级工业舰": "rorqual",         # Rorqual 长须鲸级（联合矿业特殊旗舰）
    "无畏舰":       "capital_combat",  # Dreadnought
    "航空母舰":     "capital_combat",  # Carrier
    "战力辅助舰":   "capital_combat",  # Force Auxiliary（后勤旗舰 FAX）
    "长枪无畏舰":   "capital_combat",  # Lancer Dreadnought 枪无畏
    "超级航母":     "supercapital",    # Supercarrier
    "泰坦":        "supercapital",    # Titan
}

# class_id → 元信息（名称、尺寸层级、说明）
SHIP_CLASSES = {
    "freight_jf": {
        "class_name": "货舰/跳跃货舰",
        "name_en": "Freighter / Jump Freighter",
        "size_tier": "capital_size",
        "description": "资本级尺寸（Capital size）。可进高安，可停靠大部分建筑。",
    },
    "rorqual": {
        "class_name": "长须鲸级",
        "name_en": "Rorqual",
        "size_tier": "XL",
        "description": "联合矿业特殊旗舰（Rorqual）。XL 级别，不可进高安，停靠受限。",
    },
    "capital_combat": {
        "class_name": "无畏/航母/FAX/枪无畏",
        "name_en": "Dreadnought / Carrier / Force Auxiliary / Lancer Dreadnought",
        "size_tier": "capital",
        "description": "正规旗舰（Capital）战斗型。不可进高安，停靠受限。",
    },
    "supercapital": {
        "class_name": "超级航母/泰坦",
        "name_en": "Supercarrier / Titan",
        "size_tier": "supercapital",
        "description": "超级旗舰（Supercapital）。仅 XL 建筑可停靠。",
    },
}

# dock_state 枚举键（不翻译，供程序消费）
DOCK = "dock"
TETHER = "tether"
ONE_TIME_UNDOCK = "one_time_undock"
ASSET_SAFETY_UNDOCK = "asset_safety_undock"

# ── 停靠矩阵：原型建筑 → {4 类舰船(column): dock_state} ─────────
# 「原型」= 每个 (分组, 尺寸) 的标准版建筑；同组同规格的变体（如"德拉库斯"铁壁
# vs 铁壁）通过 (groupID, rigSize) 关联到此原型，自动继承本矩阵。
# 这些值是社区整理的精确停靠知识（含 one_time_undock 特例），不来自 category 推导。
DOCK_MATRIX = {
    # NPC 站：超级旗舰仅资产安全出口可起飞一次
    "npc_station": {"freight_jf": DOCK, "rorqual": DOCK,
                    "capital_combat": DOCK, "supercapital": ASSET_SAFETY_UNDOCK},
    35832: {"freight_jf": DOCK, "rorqual": TETHER,
            "capital_combat": TETHER, "supercapital": TETHER},          # Astrahus M (堡垒)
    35825: {"freight_jf": DOCK, "rorqual": TETHER,
            "capital_combat": TETHER, "supercapital": TETHER},          # Raitaru M (工程复合体)
    35835: {"freight_jf": DOCK, "rorqual": TETHER,
            "capital_combat": TETHER, "supercapital": TETHER},          # Athanor M (精炼厂)
    35826: {"freight_jf": DOCK, "rorqual": DOCK,
            "capital_combat": ONE_TIME_UNDOCK, "supercapital": TETHER}, # Azbel L (工程复合体)
    35836: {"freight_jf": DOCK, "rorqual": DOCK,
            "capital_combat": TETHER, "supercapital": TETHER},          # Tatara L (精炼厂)
    35833: {"freight_jf": DOCK, "rorqual": DOCK,
            "capital_combat": DOCK, "supercapital": TETHER},            # Fortizar L (堡垒)
    35827: {"freight_jf": DOCK, "rorqual": DOCK,
            "capital_combat": DOCK, "supercapital": ONE_TIME_UNDOCK},   # Sotiyo XL (工程复合体)
    35834: {"freight_jf": DOCK, "rorqual": DOCK,
            "capital_combat": DOCK, "supercapital": DOCK},              # Keepstar XL (堡垒)
}


# ── SDE 加载工具 ────────────────────────────────────────────
def load_jsonl_as_dict(name):
    """读取 jsonl/ 下某文件，重建 {key: value} dict。"""
    p = os.path.join(JSONL_DIR, name + ".jsonl")
    result = {}
    if not os.path.exists(p):
        return result
    with io.open(p, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            result[obj["key"]] = obj.get("value", obj)
    return result


def load_ship_typeids():
    """从 ships_output.jsonl 提取各舰船 group 的 typeID 列表。返回 {group_name: [typeID,...]}。"""
    by_group = {}
    with io.open(SRC_SHIPS, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw)
            by_group.setdefault(obj.get("groupName"), []).append(obj["typeID"])
    return by_group


def extract_npc_station_typeids():
    """从 output/npcStationTypes.jsonl 读取 NPC 站全部 typeID。"""
    path = os.path.join(OUT_DIR, "npcStationTypes.jsonl")
    ids = []
    if os.path.exists(path):
        with io.open(path, "r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                ids.append(json.loads(raw)["key"])
    return sorted(set(ids))


def collect_upwell_buildings():
    """通过 category 关联查询，返回 categoryID=65（建筑）全部 type 的清单。

    使用 SDE：types → groups（categoryID=65）→ typedogma（rigSize / tetheringRange）。
    返回 [ {typeID, name, groupID, groupName, published, size, rigSize, tether} ]。
    """
    groups = load_jsonl_as_dict("groups")
    types = load_jsonl_as_dict("types")
    typedogma = load_jsonl_as_dict("typedogma")

    # 收集 category=65 的 groupID
    struct_groups = set()
    for gid, g in groups.items():
        if g.get("categoryID") == 65:
            struct_groups.add(gid)

    buildings = []
    for tid, t in types.items():
        gid = t.get("groupID")
        if gid not in struct_groups:
            continue
        rg = None
        tether = None
        dogma = typedogma.get(tid, {})
        for a in dogma.get("dogmaAttributes", []):
            if a["attributeID"] == 1547:
                rg = a["value"]
            elif a["attributeID"] == 2268:
                tether = a["value"]
        rig = int(rg) if rg is not None else None
        buildings.append({
            "typeID": tid,
            "name": t.get("typeNameID", ""),
            "groupID": gid,
            "groupName": groups[gid].get("groupNameID", ""),
            "published": t.get("published", 0),
            "size": SIZE_LABEL.get(rig),
            "rigSize": rig,
            "tether": tether,
        })
    buildings.sort(key=lambda b: (b["groupID"], b["typeID"]))
    return buildings


def build_default_policy():
    return {
        "kind": "default_policy",
        "id": "regular_ships_always_dock",
        "rule": "可停靠（dock）",
        "scope": "常规舰船（S/M/L 尺寸，非旗舰/超旗）",
        "description": "常规舰船不受停靠矩阵限制，在停靠矩阵列出的全部建筑（NPC 站 + 玩家建筑）中均可停靠。",
    }


def build_ship_classes(ship_typeids):
    """按 SHIP_GROUP_CLASS 聚合生成 ship_class 记录。"""
    agg = {}
    for group_name, typeids in ship_typeids.items():
        class_id = SHIP_GROUP_CLASS.get(group_name)
        if not class_id:
            continue
        agg.setdefault(class_id, {})[group_name] = sorted(typeids)

    records = []
    for class_id in SHIP_CLASSES:  # 按定义顺序输出，保证稳定
        meta = SHIP_CLASSES[class_id]
        groups = agg.get(class_id, {})
        ships = sorted(tid for tids in groups.values() for tid in tids)
        rec = {
            "kind": "ship_class",
            "class_id": class_id,
            "class_name": meta["class_name"],
            "name_en": meta["name_en"],
            "size_tier": meta["size_tier"],
            "description": meta["description"],
            "ship_typeids": ships,
            "group_ids": {
                gname: sorted(tids) for gname, tids in sorted(groups.items())
            },
        }
        records.append(rec)
    return records


def build_dock_rules(npc_station_typeids, upwell_buildings):
    """生成 dock_rule 记录：NPC 站一条 + 每个可停靠玩家建筑（含变体）各一条。

    原型锚点：以 DOCK_MATRIX 的键（原型 typeID）为基准，用 (groupID, size) 索引；
    变体（同 group 同 rigSize）经此关联继承原型的停靠矩阵。
    """
    rules = []

    # NPC 站聚合一条：structure_id 列出 NPC 站全部 typeID
    npc_matrix = DOCK_MATRIX["npc_station"]
    rules.append({
        "kind": "dock_rule",
        "structure_type": "npc_station",
        "structure_id": sorted(npc_station_typeids),
        "structure_name": "NPC 空间站",
        "size": None,
        "docking": {
            cid: npc_matrix[cid] for cid in
            ("freight_jf", "rorqual", "capital_combat", "supercapital")
        },
    })

    # 由原型 typeID 构建 (groupID, size) → 原型 的索引
    by_typeid = {b["typeID"]: b for b in upwell_buildings}
    proto_by_key = {}
    for proto_tid in DOCK_MATRIX:
        if proto_tid == "npc_station":
            continue
        b = by_typeid.get(proto_tid)
        if not b or b["size"] is None:
            continue
        proto_by_key[(b["groupID"], b["size"])] = proto_tid

    for b in upwell_buildings:
        # 只保留已发布、可实际放置的建筑
        if b["published"] != 1:
            continue
        # 无规格或同类键缺失 → 不适用停靠规则（如游寇前哨/昇威信标等）
        if b["size"] is None:
            continue
        proto_tid = proto_by_key.get((b["groupID"], b["size"]))
        if proto_tid is None:
            continue
        matrix = DOCK_MATRIX[proto_tid]
        rules.append({
            "kind": "dock_rule",
            "structure_type": "upwell",
            "structure_id": b["typeID"],
            "structure_name": b["name"],
            "name_en": PROTO_NAMES_EN.get(b["typeID"]) or PROTO_NAMES_EN.get(proto_tid),
            "size": b["size"],
            "category": "玩家建筑",
            "docking": {
                cid: matrix[cid] for cid in
                ("freight_jf", "rorqual", "capital_combat", "supercapital")
            },
        })

    rules.sort(key=lambda r: (r["structure_type"] != "npc_station", str(r["structure_id"])))
    return rules


def main():
    if not os.path.exists(SRC_SHIPS):
        print("ships_output.jsonl not found: {}".format(SRC_SHIPS))
        print("Run `python 2.3.extract_ships.py` first.")
        return 1

    for req in ("types", "groups", "typedogma"):
        if not os.path.exists(os.path.join(JSONL_DIR, req + ".jsonl")):
            print("{} not found: {}".format(req, os.path.join(JSONL_DIR, req + ".jsonl")))
            print("Run `python 1.execute_loaders.py` first.")
            return 1

    if not os.path.exists(OUT_DIR):
        os.makedirs(OUT_DIR)

    ship_typeids = load_ship_typeids()
    npc_typeids = extract_npc_station_typeids()
    upwell_buildings = collect_upwell_buildings()

    records = []
    records.append(build_default_policy())
    records.extend(build_ship_classes(ship_typeids))
    records.extend(build_dock_rules(npc_typeids, upwell_buildings))

    with io.open(DST_RULES, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")

    kinds = {}
    for rec in records:
        kinds[rec["kind"]] = kinds.get(rec["kind"], 0) + 1
    upwell_rules = sum(1 for r in records if r.get("kind") == "dock_rule"
                       and r.get("structure_type") == "upwell")
    print("  -> {} ({} lines)".format(DST_RULES, len(records)))
    print("     kinds: {}".format(kinds))
    print("     可停靠玩家建筑（含变体）dock_rule：{} 条".format(upwell_rules))
    print("Next: python 4.2.extract_docking_structures.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
