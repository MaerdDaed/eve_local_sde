# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""
从 EVE 官方下载最新静态数据包，提取 mapSolarSystems.jsonl 到 output/。

用法:
    python 2.5_download_mapSolarSystems.py
"""

import io
import os
import shutil
import sys
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "output")
URL = "https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip"
TARGET = "mapSolarSystems.jsonl"

if sys.version_info[0] >= 3:
    from urllib.request import urlopen
else:
    from urllib2 import urlopen


def main():
    if not os.path.exists(OUT_DIR):
        os.makedirs(OUT_DIR)

    dst = os.path.join(OUT_DIR, TARGET)
    zip_path = os.path.join(BASE, "_temp_sde.zip")

    print("Downloading {} ...".format(URL))
    try:
        resp = urlopen(URL)
        with io.open(zip_path, "wb") as f:
            f.write(resp.read())
        resp.close()
    except Exception as e:
        print("Download failed: {}".format(e))
        return

    print("Extracting {} ...".format(TARGET))
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if TARGET in zf.namelist():
                with zf.open(TARGET) as src, io.open(dst, "wb") as fout:
                    fout.write(src.read())
                print("Done: {} -> {}".format(TARGET, dst))
            else:
                print("'{}' not found in zip. Files in archive:".format(TARGET))
                for name in sorted(zf.namelist())[:20]:
                    print("  {}".format(name))
                if len(zf.namelist()) > 20:
                    print("  ... and {} more".format(len(zf.namelist()) - 20))
    except Exception as e:
        print("Extract failed: {}".format(e))
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)


if __name__ == "__main__":
    main()
