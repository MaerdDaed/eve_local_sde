# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""
提取种族 (raceID) 和势力 (factionID) 到中文名的映射，输出到 output/。

用法:
    python 2.6.extract_race_faction.py
"""

import io
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
JSONL_DIR = os.path.join(BASE, "jsonl")
OUT_DIR = os.path.join(BASE, "output")

SRC_RACES = os.path.join(JSONL_DIR, "races.jsonl")
SRC_FACTIONS = os.path.join(JSONL_DIR, "factions.jsonl")
DST_RACES = os.path.join(OUT_DIR, "races.jsonl")
DST_FACTIONS = os.path.join(OUT_DIR, "factions.jsonl")


def extract_mapping(src_path, id_key, name_field="nameID"):
    """从 {key, value} 包装的 JSONL 中提取 id→name 映射。

    Args:
        src_path: 源 JSONL 路径
        id_key: 输出中的 ID 字段名 (如 "raceID", "factionID")
        name_field: value 对象中的名称字段 (默认 "nameID")

    Returns:
        list of {id_key: int, "name": str}
    """
    results = []
    if not os.path.exists(src_path):
        print("Source not found: {}".format(src_path))
        return results

    with io.open(src_path, "rb") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw.decode("utf-8"))
            key = obj.get("key")
            value = obj.get("value", {})
            name = value.get(name_field, "")
            if key is not None and name:
                results.append({id_key: int(key), "name": name})

    results.sort(key=lambda x: x[id_key])
    return results


def main():
    if not os.path.exists(OUT_DIR):
        os.makedirs(OUT_DIR)

    # ── 种族 ──
    races = extract_mapping(SRC_RACES, "raceID")
    with io.open(DST_RACES, "wb") as f:
        for entry in races:
            line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
            f.write(line.encode("utf-8") + b"\n")
    print("Done: {} races -> {}".format(len(races), DST_RACES))

    # ── 势力 ──
    factions = extract_mapping(SRC_FACTIONS, "factionID")
    with io.open(DST_FACTIONS, "wb") as f:
        for entry in factions:
            line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
            f.write(line.encode("utf-8") + b"\n")
    print("Done: {} factions -> {}".format(len(factions), DST_FACTIONS))


if __name__ == "__main__":
    main()
