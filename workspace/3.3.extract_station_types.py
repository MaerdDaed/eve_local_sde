# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""
从 `jsonl/types.jsonl` 中筛选 `output/npcStations.jsonl` 实际使用到的 typeID，
生成 `output/npcStationTypes.jsonl`（行格式与 types.jsonl 一致：{"value": ..., "key": typeID}）。

用法:
    python 3.3.extract_station_types.py

退出码:
    0  生成成功
    1  缺少 npcStations.jsonl（需先运行 3.2）或 types.jsonl
"""

import io
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
JSONL_DIR = os.path.join(BASE, "jsonl")
OUT_DIR = os.path.join(BASE, "output")

SRC_TYPES = os.path.join(JSONL_DIR, "types.jsonl")
SRC_STATIONS = os.path.join(OUT_DIR, "npcStations.jsonl")
DST_STATION_TYPES = os.path.join(OUT_DIR, "npcStationTypes.jsonl")


def extract_station_types(src_stations, src_types, dst):
    """筛选 npcStations 用到的 typeID，生成类型文件。返回生成条数；缺文件返回 -1。"""
    if not os.path.exists(src_stations):
        print("npcStations.jsonl not found: {}".format(src_stations))
        print("Run `python 3.2.extract_map_files.py` first.")
        return -1
    if not os.path.exists(src_types):
        print("types.jsonl not found: {}".format(src_types))
        return -1

    type_ids = set()
    with io.open(src_stations, "rb") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            type_ids.add(int(json.loads(raw.decode("utf-8")).get("typeID", -1)))
    type_ids.discard(-1)

    matches = []
    with io.open(src_types, "rb") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw.decode("utf-8"))
            if obj.get("key") in type_ids:
                matches.append(obj)

    matches.sort(key=lambda x: x.get("key"))
    with io.open(dst, "w", encoding="utf-8") as f:
        for obj in matches:
            f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(matches)


def main():
    n = extract_station_types(SRC_STATIONS, SRC_TYPES, DST_STATION_TYPES)
    if n < 0:
        sys.exit(1)
    print("  -> {} ({} types)".format(DST_STATION_TYPES, n))
    print("Next: python 3.4.generate_readme.py")


if __name__ == "__main__":
    main()
