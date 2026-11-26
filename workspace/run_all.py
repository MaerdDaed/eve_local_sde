# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""
按编号顺序串联执行所有脚本。

用法:
    python run_all.py [zh]
"""

import glob
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable
PYTHON2 = r"C:\Python27\python.exe"

def sort_key(name):
    """从文件名提取数字前缀作为排序键，如 0.prepare → (0,), 2.4_strip → (2, 4)"""
    m = re.match(r"^\d+(?:\.\d+)*", name)
    if not m:
        return ()
    return tuple(int(x) for x in m.group().split("."))

scripts = sorted(
    [f for f in os.listdir(BASE) if f[0].isdigit() and f.endswith(".py")],
    key=sort_key
)

print("Scripts to run:")
for s in scripts:
    print("  {}".format(s))
print()

locale = sys.argv[1] if len(sys.argv) > 1 else ""

for script in scripts:
    path = os.path.join(BASE, script)
    print("=" * 60)
    print(">>> {}".format(script))
    print("=" * 60)
    python_exe = PYTHON2 if script == "1.execute_loaders.py" else PYTHON
    args = [python_exe, path]
    if script == "1.execute_loaders.py" and locale:
        args.append(locale)
    ret = subprocess.call(args)
    if ret != 0:
        print("[!!] {} failed with code {}".format(script, ret))
        break
    print()

print("=" * 60)
print("All done.")
