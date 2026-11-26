# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""
从 JSON 数据中提取所有舰船 (categoryID=6) 的完整信息。

用法：
    python extract_ships.py
    python extract_ships.py --output ships_output.json
    python extract_ships.py --ship 76009    # 只提取指定 typeID
"""

import io
import json
import os
import re
import sys


# ── 路径配置 ──────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
JSONL_DIR = os.path.join(BASE, "jsonl")
OUT_DIR = os.path.join(BASE, "output")


def fix_sci_notation(json_str):
    """将 JSON 字符串中所有科学计数法浮点数替换为普通小数"""
    def replace_sci(m):
        num = float(m.group(0))
        # 对于绝对值 >= 0.001 且 < 1e10 的，用普通小数
        if 0.001 <= abs(num) < 1e10 or abs(num) < 0.001:
            s = '{:.15f}'.format(num).rstrip('0').rstrip('.')
            return s
        return m.group(0)

    # 匹配 JSON 中的科学计数法数字，如 2.24e-06, 1.5e+10
    return re.sub(r'-?\d+\.?\d*[eE][+-]?\d+', replace_sci, json_str)


# ── 操作码含义 ────────────────────────────────────────────
OPERATIONS = {
    0: "PreAssign",    # value = modifyingAttr
    1: "PreMul",       # value *= modifyingAttr
    2: "PreDiv",       # value /= modifyingAttr
    3: "ModAdd",       # value += modifyingAttr
    4: "ModSub",       # value -= modifyingAttr
    5: "PostAssign",
    6: "PostPercent",  # value *= (1 + lvl * modifyingAttr / 100)
    7: "PostMul",
    8: "PostDiv",
}

# unitID=101 的属性需要从毫秒转为秒
MS_UNITS = {101}


def load_jsonl_as_dict(filename):
    """读取 JSONL 文件，重建 {key: value} dict"""
    path = os.path.join(JSONL_DIR, filename)
    result = {}
    if not os.path.exists(path):
        return result
    with io.open(path, "rb") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw.decode("utf-8"))
            if "key" in obj and "value" in obj:
                result[str(obj["key"])] = obj["value"]
            else:
                result[str(obj.get("key", obj.get("value")))] = obj.get("value", obj)
    return result


def format_value(attr, value):
    """格式化属性值，处理毫秒→秒转换"""
    unit = attr.get("unitID", 0)
    if unit in MS_UNITS and isinstance(value, (int, float)):
        return value / 1000.0
    return value


def interpret_bonus(operation, value, func_type):
    """根据 operation 和 func 类型解读加成含义"""
    if func_type in ("LocationRequiredSkillModifier", "OwnerRequiredSkillModifier"):
        if operation == 6:
            return "{:+.1f}% / 级".format(value)
        elif operation == 4:
            return "-{:.1f}% / 级".format(abs(value))
        elif operation == 2:
            if value == 1:
                return "+1 / 级"
            return "/{:.1f} / 级".format(value)
        else:
            return "op={} val={}".format(operation, value)
    else:
        if operation == 6:
            return "{:+.1f}%".format(value)
        elif operation == 0:
            return "= {:.1f}".format(value)
        elif operation == 1:
            return "x {:.2f}".format(value)
        elif operation == 3:
            return "+{:.1f}".format(value)
        elif operation == 4:
            return "-{:.1f}".format(abs(value))
        else:
            return "op={} val={}".format(operation, value)


def main():
    if not os.path.exists(OUT_DIR):
        os.makedirs(OUT_DIR)

    print("Loading data...")
    types = load_jsonl_as_dict("types.jsonl")
    groups = load_jsonl_as_dict("groups.jsonl")
    td = load_jsonl_as_dict("typedogma.jsonl")
    da = load_jsonl_as_dict("dogmaattributes.jsonl")
    de = load_jsonl_as_dict("dogmaeffects.jsonl")
    required = load_jsonl_as_dict("requiredskillsfortypes.jsonl")

    # ── 数据完整性检查 ──
    if len(da) == 0:
        print("[!!] WARNING: dogmaattributes.jsonl is empty — ships will have 0 attributes!")
    if len(td) == 0:
        print("[!!] WARNING: typedogma.jsonl is empty — ships will have 0 attributes/effects!")
    if len(de) == 0:
        print("[!!] WARNING: dogmaeffects.jsonl is empty — ship bonuses may be missing!")
    print("  types={}, typedogma={}, dogmaattrs={}, dogmaeffects={}, requiredSkills={}".format(
        len(types), len(td), len(da), len(de), len(required)))

    # 找出所有 categoryID=6 的 groupID
    ship_group_ids = set()
    for gid, g in groups.items():
        if g.get("categoryID") == 6:
            ship_group_ids.add(int(gid))

    print("Ship groups: {}".format(len(ship_group_ids)))

    # 筛选所有舰船 typeID
    ships = {}
    for tid, t in types.items():
        gid = t.get("groupID", 0)
        if gid in ship_group_ids and t.get("published") == 1:
            ships[int(tid)] = t

    print("Published ships: {}".format(len(ships)))

    # ── 检查是否指定单个 typeID ──
    target_tid = None
    for arg in sys.argv[1:]:
        if arg.startswith("--ship="):
            target_tid = int(arg.split("=")[1])

    if target_tid:
        if target_tid in ships:
            ships = {target_tid: ships[target_tid]}
        else:
            t = types.get(str(target_tid))
            if t:
                ships = {target_tid: t}
            else:
                print("typeID {} not found!".format(target_tid))
                return

    # ── 构建输出 ──
    output = {}
    count = 0
    for tid, ship in ships.items():
        tid_str = str(tid)
        dogma = td.get(tid_str, {})
        req = required.get(tid_str, {})

        # 基本信息
        group = groups.get(str(ship.get("groupID", 0)), {})
        entry = {
            "typeID": tid,
            "name": ship.get("typeNameID", ""),
            "groupID": ship.get("groupID", 0),
            "groupName": group.get("groupNameID", ""),
            "techLevel": ship.get("techLevel", 1),
            "metaGroupID": ship.get("metaGroupID", 0),
            "raceID": ship.get("raceID", 0),
            "factionID": ship.get("factionID", 0),
            "basePrice": ship.get("basePrice", 0),
            "mass": ship.get("mass", 0),
            "volume": ship.get("volume", 0),
            "capacity": ship.get("capacity", 0),
            "radius": ship.get("radius", 0),
            "marketGroupID": ship.get("marketGroupID", 0),
            "descriptionID": ship.get("descriptionID", 0),
        }

        # ── 基础属性 ──
        attrs = {}
        for a in dogma.get("dogmaAttributes", []):
            aid = a["attributeID"]
            val = a["value"]
            attr_def = da.get(str(aid), {})
            name_cn = attr_def.get("displayNameID") or attr_def.get("name", "")
            display_val = format_value(attr_def, val)
            attrs[str(aid)] = {
                "name": name_cn,
                "value": display_val,
            }
        entry["attributes"] = attrs

        # ── 驾驶需求 ──
        skill_reqs = []
        for sid, level in req.items():
            skill = types.get(sid, {})
            skill_reqs.append({
                "skillID": int(sid),
                "skillName": skill.get("typeNameID", ""),
                "level": level,
            })
        entry["requiredSkills"] = skill_reqs

        # ── 技能加成 & 特有加成 ──
        skill_bonuses = []
        role_bonuses = []

        for e in dogma.get("dogmaEffects", []):
            eid = str(e["effectID"])
            eff = de.get(eid, {})
            eff_name = eff.get("effectName", "")

            for mi in eff.get("modifierInfo", []):
                func = mi.get("func", "")

                if func not in ("LocationRequiredSkillModifier",
                                "OwnerRequiredSkillModifier",
                                "ItemModifier"):
                    continue

                mod_attr = mi.get("modifiedAttributeID", 0)
                mod_val = mi.get("modifyingAttributeID", 0)
                op = mi.get("operation", 0)
                domain = mi.get("domain", "")

                # 从 typedogma 中取 modifyingAttribute 的实际值
                bonus_value = None
                for a2 in dogma.get("dogmaAttributes", []):
                    if a2["attributeID"] == mod_val:
                        bonus_value = a2["value"]
                        break

                if bonus_value is None:
                    continue

                # 属性名称
                attr_cn = da.get(str(mod_attr), {}).get("displayNameID") or \
                          da.get(str(mod_attr), {}).get("name", str(mod_attr))

                bonus_text = interpret_bonus(op, bonus_value, func)

                bonus_info = {
                    "effectID": int(eid),
                    "effectName": eff_name,
                    "func": func,
                    "domain": domain,
                    "attribute": attr_cn,
                    "attributeID": mod_attr,
                    "bonusCoeff": bonus_value,
                    "operation": op,
                    "operationName": OPERATIONS.get(op, str(op)),
                    "description": bonus_text,
                }

                if func in ("LocationRequiredSkillModifier", "OwnerRequiredSkillModifier"):
                    sid = mi.get("skillTypeID", 0)
                    skill_name = types.get(str(sid), {}).get("typeNameID", str(sid))
                    bonus_info["skillTypeID"] = sid
                    bonus_info["skillName"] = skill_name
                    skill_bonuses.append(bonus_info)
                else:
                    role_bonuses.append(bonus_info)

        # ── 去重：按 effectID + skillTypeID 合并技能加成 ──
        merged_skills = {}
        for b in skill_bonuses:
            key = (b["effectID"], b.get("skillTypeID", 0))
            if key not in merged_skills:
                merged_skills[key] = {
                    "effectID": b["effectID"],
                    "effectName": b["effectName"],
                    "skillTypeID": b.get("skillTypeID", 0),
                    "skillName": b.get("skillName", ""),
                    "func": b["func"],
                    "bonuses": [],
                }
            merged_skills[key]["bonuses"].append({
                "attribute": b["attribute"],
                "attributeID": b["attributeID"],
                "description": b["description"],
            })
        entry["skillBonuses"] = list(merged_skills.values())

        # ── 去重：特有加成 ──
        seen = set()
        unique_roles = []
        for b in role_bonuses:
            key = (b["effectID"], b["attributeID"])
            if key not in seen:
                seen.add(key)
                unique_roles.append(b)
        entry["roleBonuses"] = unique_roles

        output[tid_str] = entry
        count += 1
        if count % 100 == 0:
            print("  已处理 {}/{} ...".format(count, len(ships)))

    # ── 输出 JSONL（每行一条舰船） ──
    out_path = os.path.join(OUT_DIR, "ships_output.jsonl")
    for arg in sys.argv[1:]:
        if arg.startswith("--output="):
            out_path = os.path.join(OUT_DIR, arg.split("=", 1)[1])

    with io.open(out_path, "wb") as f:
        for tid_str, entry in output.items():
            line = json.dumps(entry, ensure_ascii=False)
            line = fix_sci_notation(line)
            f.write(line.encode("utf-8") + b"\n")

    print()
    print("完成！共 {} 艘舰船 -> {}".format(len(output), out_path))

    # ── 如果只查一艘，打印详情 ──
    if target_tid and len(output) == 1:
        entry = output[str(target_tid)]
        print()
        print("=" * 60)
        print("{} (typeID={})".format(entry["name"], entry["typeID"]))
        print("=" * 60)
        print("分组: {} ({})".format(entry["groupName"], entry["groupID"]))
        print("科技等级: {}".format(entry["techLevel"]))
        print("价格: {:,.0f} ISK".format(entry["basePrice"]))
        print("质量: {:,.0f} kg".format(entry["mass"]))
        print("体积: {:,.0f} m3".format(entry["volume"]))
        print()

        if entry["requiredSkills"]:
            print("--- 驾驶需求 ---")
            for s in entry["requiredSkills"]:
                print("  {} (ID:{}) Lv.{}".format(s["skillName"], s["skillID"], s["level"]))
            print()

        print("--- Skill Bonuses ---")
        for sb in entry["skillBonuses"]:
            print("  [{}] {} (effect {})".format(
                sb["skillName"], sb["effectName"], sb["effectID"]))
            for b in sb["bonuses"]:
                print("    {}: {}".format(b["attribute"], b["description"]))
        print()

        print("--- Role Bonuses ---")
        for rb in entry["roleBonuses"]:
            print("  {}: {}".format(rb["attribute"], rb["description"]))
        print()


if __name__ == "__main__":
    main()
