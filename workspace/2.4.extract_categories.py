# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""
去掉 categories.jsonl 的 key 包装，只保留 value，输出到 output/。

用法:
    python 2.4_strip_categories.py
"""

import io
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
JSONL_DIR = os.path.join(BASE, "jsonl")
OUT_DIR = os.path.join(BASE, "output")

SRC = os.path.join(JSONL_DIR, "categories.jsonl")
DST = os.path.join(OUT_DIR, "categories.jsonl")


def main():
    if not os.path.exists(OUT_DIR):
        os.makedirs(OUT_DIR)

    if not os.path.exists(SRC):
        print("Source not found: {}".format(SRC))
        return

    count = 0
    with io.open(SRC, "rb") as fin, io.open(DST, "wb") as fout:
        for raw in fin:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw.decode("utf-8"))
            value = obj.get("value", obj)
            line = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            fout.write(line.encode("utf-8") + b"\n")
            count += 1

    print("Done: {} lines -> {}".format(count, DST))


if __name__ == "__main__":
    main()
