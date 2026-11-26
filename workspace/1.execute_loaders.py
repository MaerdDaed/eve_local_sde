# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import pickle
import glob
import importlib
import io
import json
import os
import shutil
import sys

# 强制 JSON 浮点数输出为普通小数，不使用科学计数法（如 1.67e-06）
json.encoder.FLOAT_REPR = lambda o: format(o, '.15f').rstrip('0').rstrip('.')

sys.path.append("pyd")

OUT_DIR = "jsonl"
if not os.path.exists(OUT_DIR):
    os.makedirs(OUT_DIR)


def decode_cfsd(key, data, strings):
    data_type = type(data)

    if data_type.__module__ == "cfsd" and data_type.__name__ == "dict":
        return {k: decode_cfsd(k, v, strings) for k, v in data.items()}
    if data_type.__module__.endswith("Loader"):
        return {x: decode_cfsd(x, getattr(data, x), strings) for x in dir(data) if not x.startswith("__")}

    if data_type.__module__ == "cfsd" and data_type.__name__ == "list":
        return [decode_cfsd(None, v, strings) for v in data]
    if isinstance(data, tuple):
        return tuple([decode_cfsd(None, v, strings) for v in data])

    if data_type.__name__.endswith("_vector"):
        return None

    if isinstance(data, int) or data_type.__name__ == "long":
        if key is not None and isinstance(key, str) and key.lower().endswith("nameid") and key != "dungeonNameID":
            if data in strings:
                return strings[data][0]
            return data
        return data
    if isinstance(data, float):
        return data
    if isinstance(data, str) or isinstance(data, unicode):
        return data

    raise ValueError("Unknown type: " + str(type(data)))


def load_jsonl(path):
    """读取 JSONL 文件，返回 list of json strings"""
    lines = []
    if not os.path.exists(path):
        return lines
    with io.open(path, "rb") as f:
        for raw in f:
            raw = raw.strip()
            if raw:
                lines.append(raw.decode("utf-8"))
    return lines


def get_id(obj):
    """从 JSON 对象中尝试提取 ID 字段（优先 *ID/*id 字段，其次第一个字段）"""
    if isinstance(obj, dict):
        for key in obj:
            if key.lower().endswith("id"):
                return obj[key]
        for key in obj:
            return obj[key]
    return None


def _find_name(obj):
    """从解析后的对象中提取一个可读的名称，用于简洁展示"""
    if not isinstance(obj, dict):
        return ""
    for k in obj:
        if k.lower().endswith("name") or k.lower().endswith("nameid"):
            return str(obj[k])
    return ""


def _list_id_key(elem):
    """从列表元素（dict）中找一个合适的 ID 键，用于匹配新旧列表中的元素。
    优先 attributeID / typeID / effectID / eventID 等常见主键。"""
    if not isinstance(elem, dict):
        return None
    for k in ("attributeID", "typeID", "effectID", "eventID",
              "exchangeID", "operationID", "groupID", "categoryID"):
        if k in elem:
            return k
    # fallback: 找第一个以 id 结尾的键
    for k in elem:
        if k.lower().endswith("id"):
            return k
    return None


def _diff_list_of_dicts(old_list, new_list, path):
    """对比两个 dict 列表，按公共 ID 键匹配元素后递归 diff。

    Returns: list of (op, field, old_val, new_val)
    """
    diffs = []
    id_key = _list_id_key(old_list[0] if old_list else new_list[0] if new_list else {})

    if id_key is None:
        # 没有合适的 ID 键，整列表对比
        if old_list != new_list:
            diffs.append(("~", path, old_list, new_list))
        return diffs

    # 构建 {id: elem} 映射
    old_by_id = {}
    for elem in old_list:
        old_by_id[unicode(elem.get(id_key))] = elem
    new_by_id = {}
    for elem in new_list:
        new_by_id[unicode(elem.get(id_key))] = elem

    all_ids = set(old_by_id.keys()) | set(new_by_id.keys())
    for eid in sorted(all_ids, key=unicode):
        elem_path = u"{}[{}={}]".format(path, id_key, eid)
        in_old = eid in old_by_id
        in_new = eid in new_by_id
        if in_old and in_new:
            sub = diff_fields(old_by_id[eid], new_by_id[eid], elem_path)
            if sub:
                diffs.extend(sub)
        elif in_new:
            diffs.append(("+", elem_path, None, new_by_id[eid]))
        else:
            diffs.append(("-", elem_path, old_by_id[eid], None))
    return diffs


def diff_fields(old_obj, new_obj, prefix=""):
    """对比两个 dict，递归展开嵌套对象，返回字段级差异列表。

    Returns: list of (op, field, old_val, new_val)
             op: "~" 修改, "+" 新增, "-" 删除
             field 使用点号路径如 "value.dogmaAttributes[attributeID=6]"
    """
    diffs = []
    all_keys = set()
    if isinstance(old_obj, dict):
        all_keys.update(old_obj.keys())
    if isinstance(new_obj, dict):
        all_keys.update(new_obj.keys())
    for k in sorted(all_keys, key=unicode):
        path = prefix + "." + unicode(k) if prefix else unicode(k)
        in_old = isinstance(old_obj, dict) and k in old_obj
        in_new = isinstance(new_obj, dict) and k in new_obj
        old_val = old_obj[k] if in_old else None
        new_val = new_obj[k] if in_new else None
        if in_old and in_new:
            if isinstance(old_val, dict) and isinstance(new_val, dict):
                diffs.extend(diff_fields(old_val, new_val, path))
            elif isinstance(old_val, list) and isinstance(new_val, list):
                # 对 dict 列表做元素级 diff；任一元素为 dict 即走此路径，
                # 避免空列表/首元素判断失误时落入 set() 差集导致 unhashable 崩溃
                if any(isinstance(e, dict) for e in old_val + new_val):
                    diffs.extend(_diff_list_of_dicts(old_val, new_val, path))
                elif any(isinstance(e, list) for e in old_val + new_val):
                    # 嵌套列表同样不可哈希，整列表对比
                    if old_val != new_val:
                        diffs.append(("~", path, old_val, new_val))
                elif old_val != new_val:
                    # 纯值列表：计算集合差异，列出新增/删除的元素
                    added = sorted(set(new_val) - set(old_val))
                    removed = sorted(set(old_val) - set(new_val))
                    if added and not removed:
                        diffs.append(("+", path, None, added))
                    elif removed and not added:
                        diffs.append(("-", path, removed, None))
                    else:
                        if removed:
                            diffs.append(("-", path, removed, None))
                        if added:
                            diffs.append(("+", path, None, added))
            elif old_val != new_val:
                diffs.append(("~", path, old_val, new_val))
        elif in_new:
            diffs.append(("+", path, None, new_val))
        else:
            diffs.append(("-", path, old_val, None))
    return diffs


def _format_val(v):
    """格式化值用于 Markdown 表格"""
    if v is None:
        return "-"
    if isinstance(v, (dict, list, tuple)):
        s = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    else:
        s = unicode(v)
    if len(s) > 80:
        s = s[:77] + "..."
    return s.replace("|", "\\|").replace("\n", " ")


def diff_jsonl():
    """对比 jsonl.bak/ 和 jsonl/ 中的文件，输出 changeLog.md（字段级差异）"""
    bak_dir = "jsonl.bak"
    new_dir = "jsonl"

    all_files = set()
    for f in os.listdir(bak_dir):
        if f.endswith(".jsonl"):
            all_files.add(f)
    for f in os.listdir(new_dir):
        if f.endswith(".jsonl"):
            all_files.add(f)

    lines_out = ["# changeLog", ""]
    changed_count = 0

    for fname in sorted(all_files):
        old_path = os.path.join(bak_dir, fname)
        new_path = os.path.join(new_dir, fname)

        old_raw = load_jsonl(old_path)
        new_raw = load_jsonl(new_path)

        # 构建 ID → (parsed_obj, raw_line) 映射
        old_map = {}
        for line in old_raw:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            oid = get_id(obj)
            if oid is not None:
                old_map[json.dumps(oid, ensure_ascii=False)] = (obj, line)

        new_map = {}
        for line in new_raw:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            oid = get_id(obj)
            if oid is not None:
                new_map[json.dumps(oid, ensure_ascii=False)] = (obj, line)

        old_ids = set(old_map.keys())
        new_ids = set(new_map.keys())

        added_ids = new_ids - old_ids
        deleted_ids = old_ids - new_ids
        common_ids = old_ids & new_ids

        # 找出修改条目 + 字段级差异
        modified = []  # (oid, name, diffs_list)
        for oid in common_ids:
            old_obj, _ = old_map[oid]
            new_obj, _ = new_map[oid]
            if json.dumps(old_obj, sort_keys=True, ensure_ascii=False) != \
               json.dumps(new_obj, sort_keys=True, ensure_ascii=False):
                name = _find_name(new_obj) or _find_name(old_obj)
                diffs = diff_fields(old_obj, new_obj)
                modified.append((oid, name, diffs))

        added_cnt = len(added_ids)
        deleted_cnt = len(deleted_ids)
        mod_cnt = len(modified)

        is_new_file = (len(old_raw) == 0)
        is_removed_file = (len(new_raw) == 0)

        if not is_new_file and not is_removed_file and added_cnt == 0 and deleted_cnt == 0 and mod_cnt == 0:
            continue

        changed_count += 1
        lines_out.append("## {}".format(fname))
        lines_out.append("")

        if is_new_file:
            lines_out.append("**新文件** — {} 条".format(len(new_raw)))
            lines_out.append("")
            continue
        if is_removed_file:
            lines_out.append("**已删除** — 原有 {} 条".format(len(old_raw)))
            lines_out.append("")
            continue

        lines_out.append("| 指标 | 数量 |")
        lines_out.append("|------|------|")
        lines_out.append("| 旧版本条目 | {} |".format(len(old_raw)))
        lines_out.append("| 新版本条目 | {} |".format(len(new_raw)))
        lines_out.append("| 新增 | {} |".format(added_cnt))
        lines_out.append("| 删除 | {} |".format(deleted_cnt))
        lines_out.append("| 修改 | {} |".format(mod_cnt))
        lines_out.append("")

        # ── 新增条目 ──
        if added_cnt > 0:
            lines_out.append("### 新增条目 ({} 条)".format(added_cnt))
            lines_out.append("")
            shown = 0
            for oid in sorted(added_ids):
                if shown >= 50:
                    break
                _, raw = new_map[oid]
                lines_out.append("```json")
                lines_out.append(raw)
                lines_out.append("```")
                lines_out.append("")
                shown += 1
            if added_cnt > 50:
                lines_out.append("... 共 {} 条，仅展示前 50 条".format(added_cnt))
                lines_out.append("")

        # ── 删除条目 ──
        if deleted_cnt > 0:
            lines_out.append("### 删除条目 ({} 条)".format(deleted_cnt))
            lines_out.append("")
            shown = 0
            for oid in sorted(deleted_ids):
                if shown >= 50:
                    break
                _, raw = old_map[oid]
                lines_out.append("```json")
                lines_out.append(raw)
                lines_out.append("```")
                lines_out.append("")
                shown += 1
            if deleted_cnt > 50:
                lines_out.append("... 共 {} 条，仅展示前 50 条".format(deleted_cnt))
                lines_out.append("")

        # ── 修改条目（字段级差异表格） ──
        if mod_cnt > 0:
            lines_out.append("### 修改条目 ({} 条)".format(mod_cnt))
            lines_out.append("")
            shown = 0
            for oid, name, diffs in modified:
                if shown >= 50:
                    break
                label = "**ID: {}**  {}".format(oid, name) if name else "**ID: {}**".format(oid)
                lines_out.append("#### {}".format(label))
                lines_out.append("")
                if not diffs:
                    lines_out.append("*(无字段级差异)*")
                    lines_out.append("")
                else:
                    lines_out.append("| 操作 | 字段 | 旧值 | 新值 |")
                    lines_out.append("|------|------|------|------|")
                    for op, field, old_v, new_v in diffs:
                        lines_out.append("| {} | `{}` | {} | {} |".format(
                            op, field, _format_val(old_v), _format_val(new_v)))
                    lines_out.append("")
                shown += 1
            if mod_cnt > 50:
                lines_out.append("... 共 {} 条，仅展示前 50 条".format(mod_cnt))
                lines_out.append("")

    if changed_count == 0:
        lines_out.append("所有文件均无变化。")

    with io.open("changeLog.md", "wb") as f:
        f.write("\n".join(lines_out).encode("utf-8"))

    print("  -> changeLog.md generated")


# 从命令行参数获取语言，默认 en-us
locale = sys.argv[1] if len(sys.argv) > 1 else "en-us"
pickle_file = "pickle/localization_fsd_{}.pickle".format(locale)

print("Loading '{}' ...".format(pickle_file))
with open(pickle_file, "rb") as f:
    strings = pickle.load(f)[1]

# ─── 备份旧 jsonl 目录 ───
BAK_DIR = "jsonl.bak"
if os.path.exists(BAK_DIR):
    shutil.rmtree(BAK_DIR)
if os.path.exists(OUT_DIR):
    shutil.copytree(OUT_DIR, BAK_DIR)
    print("Backed up {} -> {}".format(OUT_DIR, BAK_DIR))

total = 0
skipped = 0

for loader in glob.glob("pyd/*Loader.pyd"):
    loader_name = os.path.splitext(os.path.basename(loader))[0]
    data_name = loader_name.replace("Loader", "").lower() + ".fsdbinary"
    data_path = "data/" + data_name

    if not os.path.exists(data_path):
        skipped += 1
        continue

    total += 1
    print("Loading '{}' ...".format(data_name))

    lib = importlib.import_module(loader_name)
    data = lib.load(data_path)
    data = decode_cfsd(None, data, strings)

    out = os.path.join(OUT_DIR, data_name.replace(".fsdbinary", ".jsonl"))
    with io.open(out, "wb") as f:
        if isinstance(data, dict):
            for k, v in data.items():
                line = json.dumps({"key": k, "value": v}, ensure_ascii=False, separators=(",", ":"))
                f.write(line.encode("utf-8") + b"\n")
        elif isinstance(data, (list, tuple)):
            for item in data:
                line = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                f.write(line.encode("utf-8") + b"\n")
        else:
            # 标量或非预期类型，整行输出
            line = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            f.write(line.encode("utf-8") + b"\n")

print()
print("Done: {} extracted, {} skipped.".format(total, skipped))

# ─── 差异对比 ───
if os.path.exists(BAK_DIR):
    print("Comparing diffs...")
    diff_jsonl()
else:
    print("No backup dir, skip diff.")

print()
print("All done.")