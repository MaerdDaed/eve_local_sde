# eve_local_sde

EVE Online 国服（晨曦）客户端静态数据（SDE）提取工具链，以及面向
[ola-app](https://github.com/MaerdDaed/ola-app) 的数据发布流水线。

客户端的 `.fsdbinary` 是私有格式，只能用客户端自带的 `*Loader.pyd` 解析（Windows + Python 2.7），
所以整套流程只能在一台配有 Wine 镜像和完整客户端缓存的开发机上跑。产物放在开发机的产物目录里，由另外的流程
上传到各环境；同时发布 GitHub Release 留档。

## 目录

| 路径 | 内容 |
|---|---|
| `workspace/` | 工具链脚本：`0.prepare_workspace` → `1.execute_loaders` → `2.x` 提取 → `3.3` / `4.1` / `4.2` 停靠规则。`9.generate_readme` 与 `run_all` 保留，但流水线不调用 |
| `legacy/` | 不再使用的旧脚本。`3.1` / `3.2` 拉的是国际服（TQ）数据，`2.5` 下载官方 SDE 星图；国服星图改由 `ola-app/gen_map_from_cn.py` 生成 |
| `ola-app/gen_map_from_cn.py` | 只用国服客户端数据生成星图与 NPC 空间站 |
| `ola-app/gen_jump_fatigue_ships.py` | 从舰船数据取属性 1971「跳跃疲劳系数」，生成 `jump_fatigue_ships.jsonl` |
| `ola-app/build_package.py` | 自检、生成 `manifest.json`、组包 |
| `ola-app/publish_release.py` | 创建或覆盖 GitHub Release |
| `ola-app/update_and_publish.sh` | 生成流水线入口：生成产物、放进产物目录、发布 Release 留档。什么时候调用、怎么上传到各环境，由仓库外的流程负责 |

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

## 流水线

`ola-app/update_and_publish.sh` 每次运行做三件事。什么时候调用（定时任务）、产物怎么上传到 dev/prd，不在这个仓库里。

1. 取文件锁。上一次还没跑完就直接退出（更新客户端缓存加生成可能超过调用间隔）。
2. 读 CDN 上的最新 build。设了 `EVE_SDE_OUT_DIR` 时，产物目录里已有这个 build 就不再生成；有新 build 时：
   更新客户端缓存 → 生成 13 个文件 → 自检 → 组包 → 放进产物目录。
3. 把产物发布成 GitHub Release 留档。该 build 的 Release 三个资产齐全就跳过；上一轮没发成的，这一轮从产物目录补发，
   不必重新生成。创建 Release 和上传资产是两步，上传中途失败会留下一个资产不全的 Release，脚本会覆盖它。

生成和交接不需要 GitHub 凭据。任何一步失败都会退出（退出码非 0），不留半成品：产物目录里的 `latest/`
要么还是上一版，要么是完整的新版。

不设 `EVE_SDE_OUT_DIR` 时是旧流程：以「GitHub 上的 Release 是否齐全」判断是否已生成，生成后立即发布，产物不保留。

### 交接给上传方

上传流程只需要认产物目录里的 `latest/`：

```
$EVE_SDE_OUT_DIR/
├── .eve-sde-outbox      标记文件：这个目录由脚本管理，脚本会删掉里面的旧版本
├── latest -> 3736091    符号链接，指向最新一版的目录；换版本时原子替换
└── 3736091/             目录名是 build 号，只留最新一版
    ├── manifest.json
    ├── ola-app-jsonl-cn3736091.tar.gz
    └── ola-app-jsonl-cn3736091.tar.gz.sha256
```

- 三个文件与 GitHub Release 的资产是同一套：包内是 `manifest.json` 和 `jsonl/` 下的 13 个数据文件，`.sha256` 是 `sha256sum -c` 的格式。
- `latest/` 任何时候都是完整的一版：脚本先写进临时目录，改名之后才替换链接。
- 有没有新版本，看 `latest` 指向的 build 号。同一个 build 每次重新打包，摘要都会变（`manifest.json` 里有生成时间）；
  但产物目录里的这一版，在下一个 build 出来之前不会再变。
- 要强制重新生成当前的 build：删掉产物目录里它的目录，下一次运行会重新生成并补发。
- 产物目录必须是空目录，或者是脚本管理过的（有标记文件）。指到一个已有内容的别的目录上，脚本会拒绝运行。
- ola-app 使用一版数据之前会校验清单与逐文件摘要，传输中途损坏的包不会被用上。

传到哪里：每台部署主机（dev、prd）的 `~/docker/ola-app/sde-inbox/`。三个文件平铺放着，不要套子目录；
ola-app 默认在每天 12:00–12:25 的检查点读取 build 号最大的那一版，校验通过后切换，不用重启。

```bash
rsync -av --delete "$EVE_SDE_OUT_DIR/latest/" <部署账号>@<主机>:docker/ola-app/sde-inbox/
```

- `latest/` 结尾的斜杠不能少：少了传过去的是一个悬空的链接。
- 12:25 之后传的要等次日才会被读取。
- 用部署账号上传即可；文件要能被容器内的 UID 1000 读取。
- 旧 build 的文件留在目录里不影响行为（ola-app 只取 build 最大的），上面的 `--delete` 会顺带清掉。
- 每次都推当前的 `latest/` 即可：ola-app 对已安装的版本不做任何事，错过一次推送的主机下次自然补上。
- 这个目录要等 ola-app 包含 #397 的版本部署之后才起作用。

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
- 留档需要 `gh` 已登录一个对该仓库有推送权限的账号；只生成、不发布时不需要。令牌不写进任何脚本。

`update_and_publish.sh` 通过环境变量拿到与本机相关的路径：

| 变量 | 必需 | 说明 |
|---|---|---|
| `EVE_CLIENT_CACHE` | 是 | `EVESharedCache` 根目录 |
| `EVE_UPDATE_CLIENT` | 是 | `update_cn_client.py` 的路径 |
| `EVE_SDE_RELEASE_REPO` | 否 | 留档仓库，默认 `MaerdDaed/eve_local_sde` |
| `EVE_SDE_OUT_DIR` | 否 | 产物目录，上传流程从这里取（见「交接给上传方」）。必须是绝对路径；不设时产物不保留 |
| `EVE_SDE_PUBLISH_RELEASE` | 否 | 设为 `0` 时不发布 GitHub Release |
| `EVE_WINE_IMAGE` | 否 | Wine 镜像，默认 `evejs-wine-sde:1` |
| `EVE_SDE_WORKSPACE` | 否 | 工具链工作目录，默认 `$EVE_CLIENT_CACHE/workspace` |
| `EVE_SDE_LOCK` | 否 | 文件锁，默认 `/tmp/eve_local_sde.lock` |
| `EVE_SDE_DRY_RUN` | 否 | 设为 `1` 时走完生成、自检、组包后停住：不发布，也不动产物目录 |

手工验证一次：不发布，用独立的工作目录和产物目录，不碰正式的那两个。工作目录必须放在客户端缓存根目录下面
（工具链要到上一级找 `ResFiles/` 和 `serenity/`）：

```bash
EVE_CLIENT_CACHE=/path/to/EVESharedCache \
EVE_UPDATE_CLIENT=/path/to/update_cn_client.py \
EVE_SDE_WORKSPACE=/path/to/EVESharedCache/workspace-trial \
EVE_SDE_OUT_DIR=/path/to/eve-sde-outbox-trial \
EVE_SDE_PUBLISH_RELEASE=0 ola-app/update_and_publish.sh
```

只想看产物、连产物目录也不想写时，把 `EVE_SDE_OUT_DIR` 去掉并加 `EVE_SDE_DRY_RUN=1`：产物留在临时目录里并打印路径。

定时任务是非登录会话，可能读不到 `gh` 存在系统钥匙串里的令牌：令牌如果在 login 钥匙串里，机器重启后要有人登录
它才解锁。设了 `EVE_SDE_OUT_DIR` 时读不到也不影响生成和交接，只是留档会失败，下一轮从产物目录补发。
要留档成功，办法是把令牌放进本机一个仅本人可读的文件，由定时任务的入口脚本通过 `GH_TOKEN` 交给 `gh`；
令牌仍然不进仓库、不进脚本。

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
