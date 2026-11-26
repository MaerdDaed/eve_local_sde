# -*- coding: utf-8 -*-
"""
整理 EVE 客户端数据文件到 workspace。

用法：将本脚本放在 workspace/ 目录下运行：
    cd workspace && python prepare_workspace.py

输出（在 workspace/ 内）：
    pyd/     ← 从 serenity/bin64/ 复制所有 *Loader.pyd
    data/    ← 从 ResFiles/ 复制所有 .fsdbinary（按 resfileindex.txt 重命名）
    pickle/  ← 从 ResFiles/ 复制 res:/localizationfsd/ 下所有 .pickle 本地化文件
    static/  ← 从 ResFiles/ 复制 res:/staticdata/ 下所有 .static (SQLite) / .schema / .pickle 文件
"""

import csv
import glob
import os
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)  # workspace 的父目录，包含 ResFiles/ 和 serenity/

RESFILES = os.path.join(PARENT_DIR, "ResFiles")
SERENITY = os.path.join(PARENT_DIR, "serenity")
WORKSPACE = SCRIPT_DIR  # 脚本自身就在 workspace/ 内

INDEX_FILE = os.path.join(SERENITY, "resfileindex.txt")
PYD_SRC = os.path.join(SERENITY, "bin64")

PYD_DST = os.path.join(WORKSPACE, "pyd")
DATA_DST = os.path.join(WORKSPACE, "data")
PKL_DST = os.path.join(WORKSPACE, "pickle")
STATIC_DST = os.path.join(WORKSPACE, "static")


def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def main():
    ensure_dir(PYD_DST)
    ensure_dir(DATA_DST)
    ensure_dir(PKL_DST)
    ensure_dir(STATIC_DST)

    # ─── 1. 解析 resfileindex.txt，复制 .fsdbinary / .static / .pickle ───
    print(">>> 读取 {} ...".format(INDEX_FILE))
    copied_data = 0
    copied_pkl = 0
    copied_static = 0
    missing = 0

    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or len(row) < 2:
                    continue

                res = row[0].strip()        # res:/staticdata/xxx.fsdbinary
                rel_path = row[1].strip()   # 72/7262b56fef...

                # 提取文件名（res 路径最后一段）
                filename = res.rsplit("/", 1)[-1]

                # 处理四类文件:
                #   res:/staticdata/*.fsdbinary  → data/
                #   res:/staticdata/*.static     → static/  (SQLite)
                #   res:/staticdata/*.schema     → static/  (表结构)
                #   res:/staticdata/*.pickle      → static/  (数据缓存)
                #   res:/localizationfsd/*.pickle → pickle/  (本地化)
                is_fsdbinary = res.startswith("res:/staticdata/") and res.endswith(".fsdbinary")
                is_static = res.startswith("res:/staticdata/") and res.endswith(".static")
                is_schema = res.startswith("res:/staticdata/") and res.endswith(".schema")
                is_data_pickle = res.startswith("res:/staticdata/") and res.endswith(".pickle")
                is_locale_pickle = res.startswith("res:/localizationfsd/") and res.endswith(".pickle")

                if not (is_fsdbinary or is_static or is_schema or is_data_pickle or is_locale_pickle):
                    continue

                src = os.path.join(RESFILES, rel_path)

                if not os.path.exists(src):
                    missing += 1
                    continue

                if is_locale_pickle:
                    dst = os.path.join(PKL_DST, filename)
                    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
                        continue
                    shutil.copy2(src, dst)
                    copied_pkl += 1
                    print("  [PKL] {}".format(filename))
                elif is_static or is_schema or is_data_pickle:
                    dst = os.path.join(STATIC_DST, filename)
                    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
                        continue
                    shutil.copy2(src, dst)
                    copied_static += 1
                    if is_static:
                        label = "SQL"
                    elif is_schema:
                        label = "SCH"
                    else:
                        label = "PKL"
                    print("  [{}] {}".format(label, filename))
                else:
                    dst = os.path.join(DATA_DST, filename)
                    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
                        continue
                    shutil.copy2(src, dst)
                    copied_data += 1
                    if copied_data % 20 == 1 or copied_data <= 3:
                        print("  [FSB] {}".format(filename))

        print()
        print("  结果: .fsdbinary = {} 个, .static = {} 个, .pickle = {} 个, 缺失 = {} 个".format(
            copied_data, copied_static, copied_pkl, missing))
    else:
        print("  [!!] 找不到 resfileindex.txt")

    # ─── 2. 复制所有 PYD 文件 ───
    print()
    print(">>> 从 {} 复制 *Loader.pyd ...".format(PYD_SRC))
    pyd_count = 0
    for src in glob.glob(os.path.join(PYD_SRC, "*Loader.pyd")):
        name = os.path.basename(src)
        dst = os.path.join(PYD_DST, name)
        shutil.copy2(src, dst)
        print("  [PYD] {}".format(name))
        pyd_count += 1

    if pyd_count == 0:
        # 尝试不区分大小写
        for f in os.listdir(PYD_SRC) if os.path.isdir(PYD_SRC) else []:
            if f.lower().endswith("loader.pyd"):
                src = os.path.join(PYD_SRC, f)
                dst = os.path.join(PYD_DST, f)
                shutil.copy2(src, dst)
                print("  [PYD] {}".format(f))
                pyd_count += 1

    print("  结果: 共 {} 个 PYD 文件".format(pyd_count))

    # ─── 3. 总结 ───
    print()
    print("=" * 50)
    print("整理完成！")
    print("  pyd/     ← {} 个 PYD 文件".format(pyd_count))
    print("  data/    ← {} 个 .fsdbinary".format(copied_data))
    print("  static/  ← {} 个 .static (SQLite)".format(copied_static))
    print("  pickle/  ← {} 个 .pickle".format(copied_pkl))
    print()
    print("下一步: python execute_loaders.py zh")
    print("=" * 50)


if __name__ == "__main__":
    main()
