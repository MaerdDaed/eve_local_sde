#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从舰船数据生成 ola-app 的跳跃疲劳船体系数表 jump_fatigue_ships.jsonl。

系数就是客户端里舰船的属性 1971「跳跃疲劳系数」。消费方按 typeID 取系数，表里没有的船体按 1.0
处理，所以只输出带该属性的舰船。ships_output.jsonl 本身只含已发布舰船（2.3 的筛选条件），
带属性 1971 的未发布变体不会出现在那里，这里不需要再过滤。

行格式与 2026-09 的人工清单相同；行序按 typeID 升序（消费方按 typeID 取值，不依赖行序）。

用法:
    python3 gen_jump_fatigue_ships.py <ships_output.jsonl> <输出文件>
"""
from __future__ import annotations

import json
import sys

FATIGUE_ATTRIBUTE = "1971"


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2

    rows = []
    with open(sys.argv[1], encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            ship = json.loads(line)
            attribute = ship.get("attributes", {}).get(FATIGUE_ATTRIBUTE)
            if attribute is None:
                continue
            rows.append({
                "typeID": ship["typeID"],
                "name": ship["name"],
                "groupID": ship["groupID"],
                "groupName": ship["groupName"],
                "categoryID": 6,  # ships_output 只含 categoryID=6（舰船）的行
                "techLevel": ship["techLevel"],
                "metaGroupID": ship["metaGroupID"],
                "published": 1,
                "jumpFatigueMultiplier": attribute["value"],
            })

    rows.sort(key=lambda row: row["typeID"])
    with open(sys.argv[2], "w", encoding="utf-8", newline="\n") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"jumpFatigueShips={len(rows)} -> {sys.argv[2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
