# eve_local_sde

EVE Online 国服（晨曦）客户端静态数据（SDE）提取工具链，以及面向
[ola-app](https://github.com/MaerdDaed/ola-app) 的数据发布流水线。

客户端的 `.fsdbinary` 是私有格式，只能用客户端自带的 `*Loader.pyd` 解析（Windows + Python 2.7），
所以整套流程只能在一台配有 Wine 镜像和完整客户端缓存的开发机上跑。产物以 GitHub Release 发布，
消费方只需要能访问 GitHub。

## 目录

| 路径 | 内容 |
|---|---|
| `workspace/` | 工具链脚本：`0.prepare_workspace` → `1.execute_loaders` → `2.x` 提取 → `3.3` / `4.1` / `4.2` 停靠规则。`9.generate_readme` 与 `run_all` 保留，但流水线不调用 |
| `legacy/` | 不再使用的旧脚本。`3.1` / `3.2` 拉的是国际服（TQ）数据，`2.5` 下载官方 SDE 星图；国服星图改由 `ola-app/gen_map_from_cn.py` 生成 |
| `ola-app/gen_map_from_cn.py` | 只用国服客户端数据生成星图与 NPC 空间站 |
| `ola-app/gen_jump_fatigue_ships.py` | 从舰船数据取属性 1971「跳跃疲劳系数」，生成 `jump_fatigue_ships.jsonl` |
| `ola-app/build_package.py` | 自检、生成 `manifest.json`、组包 |
| `ola-app/publish_release.py` | 创建或覆盖 GitHub Release |
| `ola-app/update_and_publish.sh` | 流水线入口，由开发机定时任务调用 |

## 发布约定

- `main` 分支放工具链代码；每一个国服客户端 build 对应一个 Release。
- Release 的 tag 是客户端 build 号（如 `3736091`），标题是「国服客户端 build <build>」。必须是正式发布：
  草稿和预发布不会出现在 `releases/latest` 里。
- 资产有三个：`ola-app-jsonl-cn<build>.tar.gz`、同名的 `.sha256`、`manifest.json`。
- 包内是 `manifest.json` 和 `jsonl/` 下的 13 个数据文件，全部由客户端数据生成。
- `manifest.json` 记录 build、生成时间（`yyyy-MM-dd HH:mm:ss`）、工具链提交，以及每个文件的 sha256 和行数。
- 同一个 build 重新生成（比如修了工具链）时覆盖该 Release 的资产，版本号不变。消费方每次比较资产摘要，
  摘要变了就按新数据处理。

查询最新版本不需要凭据（仓库公开）：

```
GET https://api.github.com/repos/MaerdDaed/eve_local_sde/releases/latest
```

## 每日流水线

开发机 cron 在 11:00 到 11:55 之间每 5 分钟调用一次 `ola-app/update_and_publish.sh`：

1. 取文件锁。上一次还没跑完就直接退出（更新客户端缓存加生成可能超过 5 分钟的检查间隔）。
2. 读 CDN 上的最新 build。该 build 的 Release 三个资产齐全就退出，所以发布成功后，这个窗口里剩下的检查都直接退出。
   创建 Release 和上传资产是两步，上传中途失败会留下一个资产不全的 Release；下一次检查会发现它并重新生成、覆盖。
3. 有新 build 时：更新客户端缓存 → 生成 13 个文件 → 自检 → 组包 → 发布 Release。

任何一步失败都会退出并且不发布；超过 12:00 不打断，让它跑完。

### 生成步骤

| # | 步骤 | 产物 |
|---|---|---|
| 1 | `0.prepare_workspace.py`：按资源索引把客户端文件复制进工作目录 | 工作目录 |
| 2 | `1.execute_loaders.py zh`（Wine + Python 2.7）：解析 FSD 表，名称取中文 | `jsonl/` 下的原始表 |
| 3 | `2.1` `2.2` `2.3` `2.4` `2.6`：物品、蓝图、舰船、分类、种族、势力 | `items_output` `blueprints_output` `ships_output` `categories` `races` `factions` |
| 4 | `gen_map_from_cn.py`：星图 | `mapSolarSystems` `mapConstellations` `mapRegions` `mapSolarSystemJumps` `npcStations` |
| 5 | 先用上一步的 `npcStations`，再跑 `3.3` `4.1` `4.2` | `docking_rules` `docking_structures` |
| 6 | `gen_jump_fatigue_ships.py` | `jump_fatigue_ships` |

`npcStations` 是第 5 步的输入，不在 13 个发布文件里。

### 自检

`build_package.py` 在组包前做五项检查，任何一项失败都不发布：

| 检查 | 规则 |
|---|---|
| 可解析 | 每个文件逐行可解析为 JSON 对象 |
| 文件齐全 | 13 个文件全部存在，没有清单之外的文件 |
| 引用完整性 | 星系的星域、星座，以及星门边的两个端点都能找到 |
| 星门一致 | 每个星系的星门数等于它的出边数 |
| 邻接交叉校验 | `jumps.static` 的星系间记录全部包含在 `starmapcache` 的邻接表里 |

最后一项需要单独说明：`gen_map_from_cn.py` 遇到不在邻接表里的记录会把它们并进输出，所以这里按并入之前的
邻接表校验。出现缺失说明邻接表的结构变了，要人工确认以后才能发布。

## 在开发机上运行

前提：

- 客户端缓存目录（`EVESharedCache`，含 `ResFiles/` 和 `serenity/`），工具链的工作目录在它下面。
- `update_cn_client.py`：读 CDN 最新 build、增量更新客户端缓存。它不在这个仓库里。
- Wine 镜像 `evejs-wine-sde:1`：Wine + Python 2.7 + 客户端的解析库，用来跑 `1.execute_loaders.py`。
- `gh` 已登录一个对该仓库有推送权限的账号。令牌不写进任何脚本。

`update_and_publish.sh` 通过环境变量拿到与本机相关的路径：

| 变量 | 必需 | 说明 |
|---|---|---|
| `EVE_CLIENT_CACHE` | 是 | `EVESharedCache` 根目录 |
| `EVE_UPDATE_CLIENT` | 是 | `update_cn_client.py` 的路径 |
| `EVE_SDE_RELEASE_REPO` | 否 | 发布仓库，默认 `MaerdDaed/eve_local_sde` |
| `EVE_WINE_IMAGE` | 否 | Wine 镜像，默认 `evejs-wine-sde:1` |
| `EVE_SDE_WORKSPACE` | 否 | 工具链工作目录，默认 `$EVE_CLIENT_CACHE/workspace` |
| `EVE_SDE_LOCK` | 否 | 文件锁，默认 `/tmp/eve_local_sde.lock` |
| `EVE_SDE_DRY_RUN` | 否 | 设为 `1` 时走完生成、自检、组包，停在发布之前 |

手工验证一次（不发布）：

```bash
EVE_CLIENT_CACHE=/path/to/EVESharedCache \
EVE_UPDATE_CLIENT=/path/to/update_cn_client.py \
EVE_SDE_DRY_RUN=1 ola-app/update_and_publish.sh
```

定时任务是非登录会话，可能读不到 `gh` 存在系统钥匙串里的令牌：令牌如果在 login 钥匙串里，机器重启后要有人登录
它才解锁。安装定时任务前先用真实的 cron 跑一次验证。读不到时的办法是把令牌放进本机一个仅本人可读的文件，
由定时任务的入口脚本通过 `GH_TOKEN` 交给 `gh`；令牌仍然不进仓库、不进脚本。

定时任务用的是它所调用的那份检出里当前的版本。更新了工具链以后，在那份检出里 `git pull`。

`1.execute_loaders.py` 在容器里以 root 运行，它写出的 `jsonl/`、`jsonl.bak/` 和 `changeLog.md` 属主是 root（其他文件读得到）。
宿主机上的脚本只读这些文件，所以流水线不受影响；手工删除工作目录时会报 Permission denied，需要用容器或 root 来删。

## 工具链脚本

`workspace/` 下的脚本要在工作目录里运行，并且它的**父目录**下要有 `ResFiles/` 和 `serenity/`（即客户端缓存根目录）：

```
EVESharedCache/
├── ResFiles/        CDN 下载的原始资源
├── serenity/        客户端目录（含 bin64/*Loader.pyd 与 resfileindex.txt）
└── workspace/       本仓库 workspace/ 的脚本复制到这里运行
    ├── pyd/ data/ static/ pickle/    0.prepare_workspace.py 复制进来的素材
    ├── jsonl/                       1.execute_loaders.py 解析出的原始表
    ├── jsonl.bak/                   上一版 jsonl/ 的备份（自动）
    ├── output/                      各提取脚本的产物
    └── changeLog.md                 两次解析之间的字段级差异（自动）
```

`1.execute_loaders.py` 需要 Python 2.7；位置参数是语言（`zh`），决定加载哪个语言包。其余脚本用 Python 3。
`run_all.py` 按编号顺序串起目录下的全部脚本，是工具链自己的用法，不产生 ola-app 需要的星图；
ola-app 的数据请走上面的流水线。
