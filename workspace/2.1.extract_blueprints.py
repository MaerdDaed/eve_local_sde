# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""
提取所有蓝图（categoryID=9）的制造信息。

数据来源:
  - types.jsonl / groups.jsonl: 找所有 categoryID=9 的类型
  - blueprints.static (SQLite): 制造配方

用法:
    python extract_blueprints.py
    python extract_blueprints.py --output blueprints.jsonl
"""

import io
import json
import os
import sqlite3
import sys


BASE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(BASE)
RESFILES = os.path.join(PARENT, "ResFiles")
INDEX = os.path.join(PARENT, "serenity", "resfileindex.txt")
JSONL_DIR = os.path.join(BASE, "jsonl")
OUT_DIR = os.path.join(BASE, "output")


def find_db_path(keyword):
    """从 resfileindex.txt 找到 static 文件的实际路径。找不到时回退 workspace/static/。"""
    # 优先从 ResFiles 按索引查找
    if os.path.exists(INDEX):
        with io.open(INDEX, "rb") as f:
            for raw in f:
                line = raw.decode("utf-8", errors="ignore")
                if not line or keyword not in line:
                    continue
                parts = line.split(",")
                if len(parts) < 2:
                    continue
                full = os.path.join(RESFILES, parts[1].strip())
                if os.path.exists(full):
                    return full
    # 回退：workspace/static/ 下的文件（0.prepare_workspace.py 复制过来的）
    fallback = os.path.join(BASE, "static", keyword)
    if os.path.exists(fallback):
        print("  [fallback] using {}".format(fallback))
        return fallback
    return None


def load_jsonl_as_dict(name):
    """读取 JSONL 文件，重建 {key: value} dict"""
    p = os.path.join(JSONL_DIR, name + ".jsonl")
    result = {}
    if not os.path.exists(p):
        return result
    with io.open(p, "rb") as f:
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


def main():
    if not os.path.exists(OUT_DIR):
        os.makedirs(OUT_DIR)

    print("加载数据...")
    types = load_jsonl_as_dict("types")
    groups = load_jsonl_as_dict("groups")

    # 找出所有 categoryID=9 (蓝图) 的类型
    # type -> groupID -> groups[groupID].categoryID == 9
    blueprint_types = {}
    category9_group_ids = set()
    for gid, g in groups.items():
        if g.get("categoryID") == 9:
            category9_group_ids.add(int(gid))

    for tid, t in types.items():
        gid = t.get("groupID", 0)
        if gid in category9_group_ids:
            blueprint_types[int(tid)] = t

    print("  蓝图类型数: {}".format(len(blueprint_types)))

    # 打开 SQLite
    db_path = find_db_path("blueprints.static")
    if not db_path:
        print("[!!] 未找到 blueprints.static")
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # ── 构建产品→蓝图的反查索引 ──
    print("  构建产品索引...")
    product_to_bp = {}
    cur.execute("SELECT key, value FROM indexes")
    for key, value in cur.fetchall():
        if key.startswith("productTypeID."):
            pid = int(key.split(".", 1)[1])
            product_to_bp[pid] = int(value)

    # ── 批量查询 cache ──
    print("  查询蓝图配方...")
    all_ids = list(blueprint_types.keys())
    placeholders = ",".join("?" * len(all_ids))
    cur.execute(
        "SELECT key, value FROM cache WHERE key IN ({})".format(placeholders),
        [str(tid) for tid in all_ids],
    )
    cache_data = {}
    for key, value in cur.fetchall():
        cache_data[int(key)] = json.loads(value)

    conn.close()

    # ── 名称解析函数 ──
    def name_of(tid):
        t = types.get(str(tid))
        if t:
            return t.get("typeNameID", str(tid))
        return str(tid)

    # ── 输出 ──
    out_path = os.path.join(OUT_DIR, "blueprints_output.jsonl")
    for arg in sys.argv[1:]:
        if arg.startswith("--output="):
            out_path = os.path.join(OUT_DIR, arg.split("=", 1)[1])

    count = 0
    with io.open(out_path, "wb") as f:
        for tid in all_ids:
            t = blueprint_types.get(tid)
            cache = cache_data.get(tid)
            if not cache or not t:
                continue

            acts = cache.get("activities", {})
            mfg = acts.get("manufacturing", {})

            entry = {
                "blueprintTypeID": tid,
                "blueprintName": t.get("typeNameID", ""),
                "groupID": t.get("groupID", 0),
                "maxProductionLimit": cache.get("maxProductionLimit", 1),
                "manufacturing": {
                    "time": mfg.get("time", 0),
                    "skills": [
                        {
                            "typeID": s["typeID"],
                            "name": name_of(s["typeID"]),
                            "level": s["level"],
                        }
                        for s in mfg.get("skills", [])
                    ],
                    "materials": [
                        {
                            "typeID": m["typeID"],
                            "name": name_of(m["typeID"]),
                            "quantity": m["quantity"],
                        }
                        for m in mfg.get("materials", [])
                    ],
                    "products": [
                        {
                            "typeID": p["typeID"],
                            "name": name_of(p["typeID"]),
                            "quantity": p["quantity"],
                        }
                        for p in mfg.get("products", [])
                    ],
                },
            }

            # 加入复制/研究时间
            for act_name in ("copying", "research_material", "research_time", "invention"):
                if act_name in acts:
                    entry[act_name] = {"time": acts[act_name].get("time", 0)}

            line = json.dumps(entry, ensure_ascii=False)
            f.write(line.encode("utf-8") + b"\n")
            count += 1

    print()
    print("完成！共 {} 条蓝图 -> {}".format(count, out_path))


if __name__ == "__main__":
    main()
