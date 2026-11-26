# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""
提取所有物品：typeID, 中文名, groupID, categoryID, 分组名, 分类名。
输出 JSONL。

用法:
    python extract_items.py
    python extract_items.py --output items.jsonl
"""

import io
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
JSONL_DIR = os.path.join(BASE, "jsonl")
OUT_DIR = os.path.join(BASE, "output")


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
    categories = load_jsonl_as_dict("categories")

    # 构建 groupID -> categoryID 映射
    group_to_cat = {}
    for gid, g in groups.items():
        group_to_cat[int(gid)] = g.get("categoryID", 0)

    # 构建 categoryID -> categoryName 映射
    cat_name = {}
    for cid, c in categories.items():
        cat_name[int(cid)] = c.get("categoryNameID", "")

    out_path = os.path.join(OUT_DIR, "items_output.jsonl")
    for arg in sys.argv[1:]:
        if arg.startswith("--output="):
            out_path = os.path.join(OUT_DIR, arg.split("=", 1)[1])

    count = 0
    with io.open(out_path, "wb") as f:
        for tid, t in types.items():
            if t.get("published", 0) != 1:
                continue
            gid = t.get("groupID", 0)
            cid = group_to_cat.get(gid, 0)
            entry = {
                "typeID": int(tid),
                "name": t.get("typeNameID", ""),
                "groupID": gid,
                "groupName": groups.get(str(gid), {}).get("groupNameID", ""),
                "categoryID": cid,
                "categoryName": cat_name.get(cid, ""),
                "published": t.get("published", 0),
            }
            f.write(json.dumps(entry, ensure_ascii=False).encode("utf-8") + b"\n")
            count += 1

    print("完成！共 {} 条 -> {}".format(count, out_path))

    # ── 打印第一个样例 ──
    if count > 0:
        print()
        print("=" * 50)
        print("样例（第一条）:")
        tid = next(iter(types.keys()))
        t = types[tid]
        gid = t.get("groupID", 0)
        cid = group_to_cat.get(gid, 0)
        print("  typeID       : {}".format(tid))
        print("  名称          : {}".format(t.get("typeNameID", "")))
        print("  groupID      : {} → {}".format(gid, groups.get(str(gid), {}).get("groupNameID", "")))
        print("  categoryID   : {} → {}".format(cid, cat_name.get(cid, "")))
        print("  published    : {}".format(t.get("published", 0)))


if __name__ == "__main__":
    main()
