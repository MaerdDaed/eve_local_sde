# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""
生成 `output/readme.md`：output/ 目录全量数据使用说明（星图 / NPC 空间站 / 物品 / 舰船 / 蓝图 / 映射）。

用法:
    python 9.generate_readme.py
"""

import io
import os

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "output")
DST_README = os.path.join(OUT_DIR, "readme.md")

README_TEMPLATE = u"""# output/ 数据目录使用说明

本目录是 EVE 静态数据提取工具链的最终产出，由以下脚本生成（按 `run_all.py` 顺序）：

| 脚本 | 产出 |
|------|------|
| `2.1.extract_blueprints.py` | `blueprints_output.jsonl` |
| `2.2.extract_items.py` | `items_output.jsonl` |
| `2.3.extract_ships.py` | `ships_output.jsonl` |
| `2.4.extract_categories.py` | `categories.jsonl` |
| `2.6.extract_race_faction.py` | `races.jsonl`、`factions.jsonl` |
| `3.1.download_sde.py` | `_sde_latest.zip`（临时中间产物，3.2 提取后自动删除） |
| `3.2.extract_map_files.py` | `mapRegions/Constellations/SolarSystems.jsonl`、`npcStations.jsonl`、`stationOperations.jsonl`、`stationServices.jsonl` |
| `3.3.extract_station_types.py` | `npcStationTypes.jsonl` |
| `4.1.generate_docking_rules.py` | `docking_rules.jsonl`（舰船停靠规则） |
| `4.2.extract_docking_structures.py` | `docking_structures.jsonl`（支持停靠的建筑信息） |
| `9.generate_readme.py` | 本文件 `readme.md` |

`km-flag-slot-mapping.jsonl` 为手工维护的辅助映射（killmail flag → 槽位），不在脚本流程内。

## 快速生成

```bash
python run_all.py zh          # 一键全流程（含 1.execute_loaders.py 需 Python 2.7）

# 或仅刷新本目录星图/NPC 空间站部分：
python 3.1.download_sde.py && python 3.2.extract_map_files.py && \\
python 3.3.extract_station_types.py && python 9.generate_readme.py
```

## 文件总览（当前版本行数）

| 文件 | 内容 | 行数 | 行格式 | 主键 |
|------|------|------|--------|------|
| `mapRegions.jsonl` | 星域 | 114 | SDE 扁平 | `_key`（regionID，10000001+） |
| `mapConstellations.jsonl` | 星座 | 1184 | SDE 扁平 | `_key`（constellationID，20000001+） |
| `mapSolarSystems.jsonl` | 星系 | 8490 | SDE 扁平 | `_key`（solarSystemID，30000001+） |
| `npcStations.jsonl` | NPC 空间站（NPC 建筑） | 5210 | SDE 扁平 | `_key`（stationID，60000000+） |
| `stationOperations.jsonl` | 空间站运营类型 | 69 | SDE 扁平 | `_key`（operationID） |
| `stationServices.jsonl` | 空间站服务 | 27 | SDE 扁平 | `_key`（serviceID） |
| `npcStationTypes.jsonl` | NPC 空间站建筑类型 | 44 | 客户端包装 | `key`（typeID） |
| `docking_rules.jsonl` | 舰船停靠规则（默认放行 + XL 舰船分类 + 逐建筑停靠矩阵） | 28 | 简化对象 | `kind` |
| `docking_structures.jsonl` | 支持停靠的建筑信息（22 玩家建筑含变体 + 44 NPC 站） | 66 | 简化对象 | `structure_key`（typeID） |
| `blueprints_output.jsonl` | 蓝图制造信息 | 5146 | 简化对象 | `blueprintTypeID` |
| `items_output.jsonl` | 全部物品列表 | 28418 | 简化对象 | `typeID` |
| `ships_output.jsonl` | 舰船完整属性 | 438 | 简化对象 | `typeID` |
| `categories.jsonl` | 物品分类 | 49 | 简化对象 | `categoryID` |
| `races.jsonl` | 种族映射 | 14 | 简化映射 | `raceID` |
| `factions.jsonl` | 势力映射 | 29 | 简化映射 | `factionID` |
| `km-flag-slot-mapping.jsonl` | killmail flag → 槽位映射 | 141 | 简化对象 | `flag` |

## 三种数据行格式

本目录混有三种 JSONL 行格式，读取时需区分：

1. **SDE 扁平格式**（星图/NPC 空间站 6 个文件 + `stationOperations` / `stationServices`）：
   每行 JSON 直接以 `_key` 作为主键，如 `{"_key": 30000001, "name": {...}, ...}`。

2. **客户端包装格式**（`npcStationTypes`，与 `jsonl/` 目录一致）：
   每行为 `{"value": {...}, "key": typeID}`，实际数据在 `value` 内，`key` 与 `value.typeID` 相同。

3. **简化对象格式**（`items_output` / `ships_output` / `blueprints_output` / `categories` / `races` / `factions` / `km-flag-slot-mapping`）：
   每行是扁平字典，直接用行内 ID 字段（如 `typeID`、`raceID`）作为主键，无外层包装。

多语言名称字段（星图部分的 `name` / `operationName` / `serviceName` / `description`）均为
`{"de":..., "en":..., "es":..., "fr":..., "ja":..., "ko":..., "ru":..., "zh":...}` 结构，取中文用 `name["zh"]`；
其余文件（`items_output` / `ships_output` / `npcStationTypes` / `races` / `factions` / `categories`）中的名称字段已是本地化中文。

## Python 加载示例

```python
import json

def load_jsonl(path):
    \"\"\"通用读取：返回 list[dict]，兼容全部三种行格式（保留原始行结构）。\"\"\"
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def as_dict(rows):
    \"\"\"将 {'value': v, 'key': k} 包装格式还原为 {k: v}。\"\"\"
    return {r["key"]: r["value"] for r in rows}
```

## 字段说明

### 星图与 NPC 空间站（3.2 / 3.3 产出）

#### mapRegions.jsonl（星域）
- `_key`：regionID
- `name`：星域名（多语言）
- `constellationIDs`：包含的星座 ID 列表
- `factionID`：占领势力（可关联 `factions.jsonl`）
- `wormholeClassID`、`nebulaID`、`position`、`description`（多语言简介）

#### mapConstellations.jsonl（星座）
- `_key`：constellationID
- `name`：星座名（多语言）
- `regionID`：所属星域
- `solarSystemIDs`：包含的星系 ID 列表
- `factionID`、`wormholeClassID`、`position`

#### mapSolarSystems.jsonl（星系）
- `_key`：solarSystemID
- `name`：星系名（多语言）
- `constellationID`：所属星座
- `regionID`：所属星域
- `securityStatus`：安全等级（如 0.858324）
- `securityClass`、`starID`、`stargateIDs`、`planetIDs`、`position`、`border` / `hub` 等

#### npcStations.jsonl（NPC 空间站）
- `_key`：stationID
- `solarSystemID`：所在星系
- `typeID`：建筑类型（关联 `npcStationTypes.jsonl`）
- `ownerID`：所属 NPC 军团（关联 `jsonl/npccorporations.jsonl`）
- `operationID`：运营类型（关联 `stationOperations.jsonl`）
- `orbitID`：环绕天体（星体 ID）、`celestialIndex`、`orbitIndex`、`position`
- `reprocessingEfficiency`：精炼效率、`reprocessingStationsTake`：精炼税
- `useOperationName`：站名是否按运营类型显示

#### stationOperations.jsonl（运营类型）
- `_key`：operationID
- `operationName`：运营名（多语言，如「种植园」）
- `services`：提供的服务 ID 列表（关联 `stationServices.jsonl`）
- `stationTypes`：可用的建筑 typeID → 概率映射
- `activityID`、`manufacturingFactor` / `researchFactor` / `ratio` / `hub` / `border` / `corridor` / `fringe`：工业与服务系数

#### stationServices.jsonl（空间站服务）
- `_key`：serviceID
- `serviceName`：服务名（多语言，如「市场」「克隆」「提炼工厂」）

#### npcStationTypes.jsonl（空间站建筑类型）
- `key` / `value.typeID`：typeID（如 1531、3867、52678「吉他贸易中心」）
- `value.typeNameID`：类型名（中文）
- `value.groupID`：组 ID（NPC 空间站均为 15）
- `value.raceID`、`graphicID`、`basePrice`、`capacity`、`radius`、`volume`、`mass`、`portionSize`、`published`

### 舰船停靠规则 / 停靠建筑（4.1 / 4.2 产出）

#### docking_rules.jsonl（舰船停靠规则，28 条）
「默认放行 + 仅 XL 规格舰船受限」模型。每行一个对象，用 `kind` 区分三类记录：

1. `kind="default_policy"`：全局不变式——常规舰船（S/M/L 尺寸，非旗舰/超旗）在停靠矩阵列出的全部建筑中均可停靠。
2. `kind="ship_class"`：XL 舰船分类定义。`class_id`（`freight_jf` / `rorqual` / `capital_combat` / `supercapital`）、
   `class_name`、`name_en`、`size_tier`（`capital_size` / `capital` / `supercapital` / 长须鲸级为 `XL`）、`description`、
   `ship_typeids`（该分类下全部舰船 typeID）、`group_ids`（{group 名: [typeID,...]}）。
3. `kind="dock_rule"`：**按建筑一条**，含 `structure_type`（`npc_station` / `upwell`）、`structure_id`
   （NPC 站为 typeID 列表，玩家建筑为单个 typeID）、`structure_name`、`name_en`、`size`（M/L/XL）、
   `docking`（该建筑对 4 类 XL 舰船的 `{class_id: dock_state}` 映射）。

`dock_state` 枚举：
- `dock`：停靠
- `tether`：仅系泊（有停靠权限即可系泊，受护盾保护/被动维修，但不进站）
- `one_time_undock`：仅可建造出厂一次（在该建筑建造后起坞一次，之后无法再停靠）
- `asset_safety_undock`：仅资产安全出口可起飞一次（从资产安全取出后起坞一次）

#### docking_structures.jsonl（支持停靠的建筑信息，66 条）
结合停靠规则，从 SDE 提取的停靠矩阵全部行：22 个已发布玩家建筑（categoryID=65，含
"德拉库斯"铁壁 / "天空之境"星城等变体）+ 44 个 NPC 空间站 typeID。
- `structure_key` / `typeID`：建筑 typeID（主键）
- `structure_type`：`upwell`（玩家建筑）/ `npc_station`（NPC 空间站）
- `name`：类型名（中文，原型玩家建筑有英文名 `name_en`）
- `size`：建筑尺寸 M/L/XL（玩家建筑；NPC 站为 null）
- `category` / `groupID` / `groupName` / `categoryID` / `categoryName`：SDE 组与分类信息
- `published`：是否发布
- `docking`：该建筑对 4 类 XL 舰船的 `{class_id: dock_state}` 映射（取自 `docking_rules.jsonl` 的 `dock_rule`）

> 玩家建筑清单不硬编码：由 `4.1` 从 `types.jsonl`（categoryID=65）经 `groups`/`typedogma` 关联查询，
> 变体按 (groupID, rigSize) 继承对应原型的停靠矩阵，故新增建筑/变体会自动纳入。

### 物品 / 舰船 / 蓝图（2.1-2.4 产出）

#### items_output.jsonl（全部物品，28418 条）
- `typeID`、`name`：物品 ID 与中文名
- `groupID` / `groupName`：组 ID 与组名
- `categoryID` / `categoryName`：分类 ID 与分类名
- `published`：是否发布（1=游戏中可见）

#### ships_output.jsonl（舰船，438 条）
- `typeID`、`name`：舰船 ID 与中文名
- `groupID` / `groupName`：组（如 25=护卫舰）
- `techLevel`、`metaGroupID`：科技等级与元组（T1/T2/势力/旗舰等）
- `raceID`、`factionID`：种族与势力
- `basePrice`、`mass`、`volume`、`capacity`、`radius`、`marketGroupID`、`descriptionID`
- `attributes`：属性字典 `{attributeID: {"name": 属性名, "value": 值}}`（如 结构值、能量栅格、各槽位数量）
- `requiredSkills`：`[{"skillID", "skillName", "level"}]`
- `skillBonuses` / `roleBonuses`：技能加成 / 角色加成，`[{effectID, effectName, skillTypeID, skillName, func, bonuses: [{attribute, attributeID, description}]}]`

#### blueprints_output.jsonl（蓝图，5146 条）
- `blueprintTypeID`、`blueprintName`：蓝图 ID 与中文名
- `groupID`：蓝图组（104=克隆、477=舰船制造等）
- `maxProductionLimit`：单次最大并行制造数量
- `manufacturing`：制造配方 `{time, skills, materials: [{typeID, name, quantity}], products: [{typeID, name, quantity}]}`
- `copying`：复制 `{time}`
- `research_material` / `research_time`：材料效率 / 时间效率研究 `{time}`

#### categories.jsonl（分类，49 条）
- `categoryID`、`categoryNameID`：分类 ID 与中文名（如 6=舰船、25=小行星）
- `published`：是否发布
- `iconID`（部分条目存在）：图标 ID

### 基础映射与辅助映射（2.6 产出 / 手工维护）

#### races.jsonl（种族，14 条）
- `raceID` → `name`：如 1=加达里、2=米玛塔尔、4=艾玛、8=盖伦特、16=朱庇特

#### factions.jsonl（势力，29 条）
- `factionID` → `name`：如 500001=加达里合众国、500003=艾玛帝国、500006=统合部

#### km-flag-slot-mapping.jsonl（killmail flag 映射，141 条，手工维护）
- `flag`：物品在击杀记录（killmail）中的 flag 值
- `flagName` / `flagText`：flag 的英文名与中文说明
- `slotKey` / `slotName`：对应槽位（如 低槽/中槽/高槽/货柜），无槽位为 null
- `displayGroup`：展示分组（cargo / lowslot / midslot / highslot / rig / subsystem 等）

## 关联关系

```
# 星图链
mapRegions._key
   └─ mapConstellations.regionID ─┐
        └─ mapSolarSystems.constellationID
             └─ npcStations.solarSystemID ─┬─ npcStations.typeID → npcStationTypes.key
                                           ├─ npcStations.operationID → stationOperations._key ─→ stationOperations.services → stationServices._key
                                           └─ npcStations.ownerID → jsonl/npccorporations.jsonl
# 星图的 factionID 可关联 factions.jsonl

# 物品链（items_output 已内联 group/category 名称，无需 join）
items_output.groupID / categoryID → groups.jsonl / categories.jsonl
ships_output.raceID → races.jsonl
ships_output.factionID → factions.jsonl
ships_output.attributes → jsonl/dogmaattributes.jsonl（attributeID）
blueprints_output.manufacturing.materials[].typeID / products[].typeID → items_output.typeID

# 停靠链（4.1 规则 → 4.2 建筑信息）
docking_rules.kind="ship_class" 的 ship_typeids → ships_output.typeID
docking_rules.kind="dock_rule".structure_id → docking_structures.structure_key（NPC 站为 typeID 列表）
docking_structures.docking → docking_rules.kind="dock_rule".docking（逐建筑停靠行为）
```

## 查询示例

```python
import json

def load_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
def as_dict(rows):
    return {r["key"]: r["value"] for r in rows}

# 载入星图
regions   = {r["_key"]: r for r in load_jsonl("mapRegions.jsonl")}
consts    = {c["_key"]: c for c in load_jsonl("mapConstellations.jsonl")}
systems   = {s["_key"]: s for s in load_jsonl("mapSolarSystems.jsonl")}
# 载入物品/舰船/映射
items     = {i["typeID"]: i for i in load_jsonl("items_output.jsonl")}
ships     = {s["typeID"]: s for s in load_jsonl("ships_output.jsonl")}
races     = {r["raceID"]: r["name"] for r in load_jsonl("races.jsonl")}
flags     = {f["flag"]: f for f in load_jsonl("km-flag-slot-mapping.jsonl")}

# 例 1：查星系（如 30000001）里的 NPC 空间站及类型名
st_types = as_dict(load_jsonl("npcStationTypes.jsonl"))
stations = load_jsonl("npcStations.jsonl")
for st in stations:
    if st["solarSystemID"] == 30000001:
        print(st["_key"], st_types[st["typeID"]]["typeNameID"])

# 例 2：查空间站完整归属链：站 → 星系 → 星座 → 星域
st = stations[0]
sys_ = systems[st["solarSystemID"]]
print(st["_key"], st_types[st["typeID"]]["typeNameID"],
      sys_["name"]["zh"], consts[sys_["constellationID"]]["name"]["zh"],
      regions[sys_["regionID"]]["name"]["zh"])

# 例 3：按组名查舰船（如全部护卫舰）及所属种族
for s in ships.values():
    if s["groupName"] == "护卫舰":
        print(s["typeID"], s["name"], races.get(s["raceID"], ""))
# 或按名字模糊查询（如势力舰船名含"海军"）
for s in ships.values():
    if "海军" in s["name"]:
        print(s["typeID"], s["name"])

# 例 4：查某蓝图（如 681）制造所需材料名称与数量
bps = {b["blueprintTypeID"]: b for b in load_jsonl("blueprints_output.jsonl")}
bp = bps[681]
for m in bp["manufacturing"]["materials"]:
    print(items[m["typeID"]]["name"], m["quantity"])

# 例 5：用 flag 映射解释 killmail 中的物品位置
print(flags.get(5, {}))   # 例：flag=5 的槽位含义
```

## 数据来源与更新

- 星图/NPC 空间站 6 个文件 + `npcStationTypes`：官方 SDE 最新 jsonl 包
  （`https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip`），由 `3.1`-`3.3` 生成。
- `items_output` / `ships_output` / `blueprints_output` / `categories` / `races` / `factions`：
  由 `jsonl/` 中间数据（客户端 fsdbinary 解析产物）经 `2.1`-`2.6` 生成。
- `km-flag-slot-mapping.jsonl`：手工维护，与游戏版本无关，一般无需更新。
- `docking_rules.jsonl` / `docking_structures.jsonl`：规则由 `4.1` 维护（舰船分类从 `ships_output.jsonl` 提取、
  建筑清单由 `4.1` 从 `types.jsonl`（categoryID=65）经 `groups`/`typedogma` 关联查询，NPC 站来自 `npcStationTypes.jsonl`），
  建筑信息由 `4.2` 生成，依赖 `4.1` 的 `dock_rule`。
  新增建筑/变体会自动纳入（变体按 (groupID, rigSize) 继承原型矩阵）；需手动同步的仅
  `4.1` 的 `SHIP_GROUP_CLASS`（舰船分组→分类）、`DOCK_MATRIX`（原型停靠矩阵）、`PROTO_NAMES_EN`（原型英文名）。
- 更新：`python run_all.py zh` 一键全量刷新；仅星图部分运行 `3.1` → `3.2` → `3.3`；
  停靠规则/建筑部分运行 `4.1` → `4.2`。
"""


def main():
    if not os.path.exists(OUT_DIR):
        os.makedirs(OUT_DIR)
    with io.open(DST_README, "w", encoding="utf-8") as f:
        f.write(README_TEMPLATE)
    print("  -> {}".format(DST_README))


if __name__ == "__main__":
    main()
