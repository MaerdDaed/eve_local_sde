# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""
下载 EVE 官方 SDE jsonl 包到工作区根目录 `_sde_latest.zip`（临时中间产物）。

该 zip 供 `3.2.extract_map_files.py` 提取使用；提取完成后由 3.2 自动删除。
所有脚本中下载官方 SDE jsonl 包的逻辑统一收敛到本脚本。

用法:
    python 3.1.download_sde.py

退出码:
    0  下载成功
    1  下载失败
"""

import io
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
SDE_URL = "https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip"
ZIP_PATH = os.path.join(BASE, "_sde_latest.zip")

if sys.version_info[0] >= 3:
    from urllib.request import urlopen
else:
    from urllib2 import urlopen


def download_sde(zip_path, url):
    """下载官方 SDE jsonl 包到指定路径。成功返回 True。"""
    print("Downloading {} ...".format(url))
    try:
        resp = urlopen(url)
        with io.open(zip_path, "wb") as f:
            f.write(resp.read())
        resp.close()
        size = os.path.getsize(zip_path)
        print("Downloaded: {} ({:.1f} MB)".format(zip_path, size / 1024.0 / 1024.0))
        return True
    except Exception as e:
        print("Download failed: {}".format(e))
        return False


def main():
    if not download_sde(ZIP_PATH, SDE_URL):
        sys.exit(1)
    print("Next: python 3.2.extract_map_files.py")


if __name__ == "__main__":
    main()
