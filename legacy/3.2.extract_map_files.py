# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""
从 `3.1.download_sde.py` 下载的 `_sde_latest.zip` 中提取星图与 NPC 空间站数据到 output/。

提取完成后自动删除 `_sde_latest.zip`（临时中间产物）。

用法:
    python 3.2.extract_map_files.py

退出码:
    0  提取成功
    1  SDE zip 不存在或提取失败（需先运行 3.1）
"""

import io
import os
import sys
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "output")
ZIP_PATH = os.path.join(BASE, "_sde_latest.zip")

# 从 SDE 包中提取的文件 (文件名 → 内容说明)
SDE_FILES = [
    ("mapRegions.jsonl", "星域"),
    ("mapConstellations.jsonl", "星座"),
    ("mapSolarSystems.jsonl", "星系"),
    ("npcStations.jsonl", "NPC 空间站"),
    ("stationOperations.jsonl", "空间站运营类型"),
    ("stationServices.jsonl", "空间站服务"),
]


def extract_from_zip(zip_path):
    """从 SDE zip 中提取相关文件到 output/。返回成功提取的文件数。"""
    if not os.path.exists(zip_path):
        print("SDE zip not found: {}".format(zip_path))
        print("Run `python 3.1.download_sde.py` first.")
        return -1

    count = 0
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name, desc in SDE_FILES:
                if name not in zf.namelist():
                    print("  [skip] '{}' not in archive".format(name))
                    continue
                dst = os.path.join(OUT_DIR, name)
                with zf.open(name) as src, io.open(dst, "wb") as fout:
                    fout.write(src.read())
                print("  -> {} ({})".format(dst, desc))
                count += 1
    except zipfile.BadZipfile as e:
        print("Bad SDE zip: {}".format(e))
        return -1
    return count


def main():
    if not os.path.exists(OUT_DIR):
        os.makedirs(OUT_DIR)

    count = extract_from_zip(ZIP_PATH)
    if count < 0:
        sys.exit(1)

    # 提取完成，清理临时 zip（中间产物）
    if os.path.exists(ZIP_PATH):
        os.remove(ZIP_PATH)
        print("Removed temp zip: {}".format(ZIP_PATH))

    print("Extracted {} files from SDE.".format(count))
    print("Next: python 3.3.extract_station_types.py")


if __name__ == "__main__":
    main()
