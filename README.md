# 雪报 Snow

多模型融合的滑雪场降雪预报，页面在 **https://tokenfly.ai/snow/**（PWA，可安装到手机）。

- Ikon / Epic 2026-27 全部雪场，229 个预报点（多山头目的地拆开，例如 Aspen Snowmass 4 个、白马 10 个、多洛米蒂 12 个）。
- 不依赖单一模型：前 10 天把最多 8 个确定性模型订正到雪场的山脚 / 山腰 / 山顶后融合；范围和信心来自 4 个集合预报共 143 个成员。
- 越远越不给假精度：第 11–16 天只给概率（≥2.5 cm、≥15 cm），第 3–5 周只给周累计的概率。
- 由 GitHub Actions 每 6 小时自动运行：重点雪场每次全量更新，其余每天一次，总量控制在免费额度内。
- 数据全部来自免费开放的来源（见[数据来源](#数据来源与署名)）。

第二阶段（集合预报 + 概率、全部雪场、分档更新、地图和排行榜）已完成，设计与交接说明在 [`docs/phase2-handoff.md`](docs/phase2-handoff.md)。现在是**第三阶段**：把预报做准并能验证（预报存档、实测、评分），以及"去哪滑"决策页。进度见[路线图](#路线图)。

## 架构

```
TokenFlyAI/snow（本仓库，公开）                       ccyjava/tokenfly（主站，私有）
┌──────────────────────────────────────────┐        ┌─────────────────────────────┐
│ data/resorts.yaml      雪场库            │        │ aiverse/snow/  静态外壳     │
│ data/featured.yaml     重点雪场          │        │ snow_site.py   /snow 路由   │
│ pipeline/              Python 数据管道   │        └──────────────┬──────────────┘
│   ingest/   确定性模型 + 集合预报抓取    │                       │
│   process/  订正·雪线·雪水比·融合·集合   │   scripts/deploy_shell.sh（仅代码变动时）
│   publish/  生成静态 JSON                │                       │
│ web/                   Next.js 静态导出  │───────────────────────┘
│ .github/workflows/                       │
│   forecast.yml  每 6 小时 ──────────────────▶ GitHub Pages
│   ci.yml        测试 + 前端构建          │     https://tokenflyai.github.io/snow/data/v1/
└──────────────────────────────────────────┘                       ▲
                                                                   │ fetch (CORS)
                              浏览器  https://tokenfly.ai/snow/ ───┘
```

为什么分成两处：tokenfly.ai 是 Render 上的 Python 服务，推送主站仓库会重启整个主站。预报数据每 6 小时变一次，所以**数据**走本仓库的 GitHub Pages（Actions 以 artifact 发布，不进 git 历史），主站仓库里只放**不含数据的页面外壳**，只有改了前端代码或雪场名单才需要重新部署。以后迁移到 Cloudflare R2 只需改 `NEXT_PUBLIC_DATA_BASE`。

### 分档更新与 API 额度

Open-Meteo 免费档每天 10,000 次加权调用（10 个变量、14 天各算 1 次；集合预报每个成员都算一个变量），我们给自己定的上限是 8,000。

| 档 | 雪场 | 确定性模型 | 集合预报 | 每点每天约 |
|---|---|---|---|---|
| featured | `data/featured.yaml`（28 个） | 每 6 小时，所有覆盖它的模型（最多 8 个） | 每天一次：ECMWF ENS、GEFS、GEPS、ICON-EPS | 115 次 |
| standard | 其余 201 个 | 每天一次：ECMWF IFS + GFS + ICON + GEM + 一个区域模型 | 每天一次：GEFS | 22 次 |

- 每天一次的刷新落在当地早晨之前：欧洲 02:37 UTC，北美东部和南美 08:37，北美西部 14:37，亚洲和大洋洲 20:37。GitHub 的定时任务经常晚几个小时或整次跳过，所以规则是"文档早于该地区时段最近一次开始的时间就刷新"：哪次运行先到就由哪次补上，一天仍只刷新一次（`config.last_slot_time`）。
- standard 档的模型数是按回测定的：只有 ECMWF + GFS 的融合误差比 5 个模型高 8%–16%。
- 每次运行先读上一版已发布的数据（`--previous`，默认是线上 GitHub Pages），不到期的雪场原样带过，所以每次发布的都是完整的一套。集合成员的日总量缓存在 `ens/{id}.json`。
- 按计划估算每天约 7,660 次；`tests/test_budget.py` 在估算超过 8,000 时失败。每次运行的实际用量记在 `manifest.json` 的 `api_usage`，限速器保证每分钟 ≤ 480、每小时 ≤ 4,800。
- 一次运行最多用每小时上限的 95%（4,560 次）：漏跑或失败之后所有 standard 雪场会同时到期（约 5,700 次），超出的部分按"最久没更新的先做"推到下一次运行（`manifest.json` 的 `run.deferred`），否则限速器要等一小时、任务会超时。
- ECMWF IFS 用 9 公里原生格点（`ecmwf_ifs`）：回测中单模型误差低 0%–7%、偏干从 0.82 改善到 0.88。Open-Meteo 的 9 公里版本没有气压层变量，所以地面变量取 9 公里、温度廓线取同一次运行的 0.25° 版本（两次请求，权重和原来一次差不多）。
- 一次全量运行（`--mode full`，或线上数据丢失后的第一次运行）约 4,500 次。

### 发布的数据（`data/v1/`）

| 文件 | 内容 |
|---|---|
| `manifest.json` | 运行时间、本次刷新了哪些雪场、各模型和集合是否可用、API 用量（本次 + 每日估算）、来源署名。最后写入，存在即表示本次运行完整 |
| `resorts.json` | 所有雪场的元数据、分档 + 24h / 72h / 7 天降雪、3 / 7 / 16 天滑雪日累计和集合范围、第 3–5 周展望（首页、地图、排行用） |
| `resort/{id}.json` | 逐小时 168h（三个海拔的气温、降雪、降水类型、雪线、0°C 层、山顶风）；逐日：前 10 天点值（夜间 / 白天降雪、集合 10–90% 范围、信心、雪质），第 11–16 天只有集合分位数和概率；第 3–5 周展望；各模型逐日降雪 |
| `ens/{id}.json` | 集合各成员的滑雪日降雪（未订正的原始值），供下一次运行复用，前端不读 |
| `planner.json` | "去哪滑"页用的紧凑数据：每个雪场每个滑雪日的粉雪分、开门时新雪、全天降雪和范围、≥2.5 / 15 cm 概率、雪质、阵风、雨（约 280 KB，压缩后约 45 KB）。字段和粉雪分的定义见 `pipeline/publish/planner.py` |
| `ics/{lang}/{pass}/{area}.ics` | 粉雪日日历订阅（B6）：语言 en / zh × 通行证 all / ikon / epic × 地区（`all`、`g-{组}`、单个大区，组的定义在 `data/region_groups.yaml`）。提前 4 天以内、粉雪分 ≥ 60、≥15 cm 概率 ≥ 60% 的雪场和日子各一个全天日程；UID 固定，预报变差后日程消失。"去哪滑"页按当前筛选给出订阅链接（Apple 日历 / Google 日历 / 复制） |
| `trend/{id}.json` | 预报趋势（B5）：最近 5 天里最多 12 次预报对每个滑雪日的山腰降雪，从存档读。详情页的全天降雪后面显示"比约一天前那次预报多 / 少多少" |
| `verification.json` | 评分（A3）：存档的预报对照存档的实测，最近 30 天和本雪季，总体 / 按大区 / 按雪场，按提前 1、2、3、5、7、10 天分别算：降雪和降水的平均绝对误差与偏差、大雪日（≥15 cm）命中和空报、≥15 / 2.5 cm 概率的 Brier 分数、范围覆盖率、各原始模型的误差和相对 NBM 的技巧分。另有最近 30 天每个雪场每天的"实测 vs 提前 1 / 3 天的预报"。定义见 `pipeline/verify/score.py`；页面是 `/accuracy`（成绩单）。存档从 2026-11-15 开始，头几周样本很少 |
| `obs/{id}.json` | 有 SNOTEL 站的雪场（美国西部 34 个）：附近 1–3 个站最近 14 个滑雪日的实测（夜间 / 全天新雪、降水、雪深、气温、质量标记）。见下面"实测" |

### 实测（SNOTEL）

`data/stations.yaml` 由 `scripts/match_stations.py` 生成：每个美国雪场 15 公里内的 SNOTEL 站，按和山腰的高差排序，最多 3 个，分级 A（5 公里内、高差 300 米内）/ B（15 公里内、高差 500 米内）/ C（只展示）。现在 34 个美国西部雪场有 A 或 B 级站；Mammoth、June、阿斯彭四个、Snowbasin、Mt. Bachelor 和南加州三个没有，要等加州 CDEC 等其他来源。

每次运行用 NRCS AWDB 接口（公有领域，免密钥，不占 Open-Meteo 额度）拉这些站最近两周的**逐小时**读数，按和预报相同的滑雪日窗口汇总（`pipeline/verify/obs.py`）：降水用雨量计（7 小时中位数滤波后取单调上升，大风中少测）；新雪用雪深的正增量（5 小时中位数滤波 + 2 英寸死区，只在雨量计有 ≥ 3 mm 时计入），是下限；下雪时雪深反降的日子标 `depth_fell`，评分不用。SNOTEL 的逐小时时间是站点的固定时区（本土 UTC−8、阿拉斯加 UTC−9，不随夏令时变）。拉取失败时保留上一版文件，不影响发布。详情页在逐日预报下面显示"附近实测"。

### 预报存档

每次运行把**本次重新计算的**雪场预报逐日写成一行，存到本仓库的孤立分支 [`archive`](https://github.com/TokenFlyAI/snow/tree/archive)：`forecasts/YYYY/MM/DD/HHMMZ.jsonl.gz`（约 240 KB/天）；实测的滑雪日存在 `obs/YYYY/MM/YYYY-MM-DD.jsonl.gz`（最近两周每次重写，测站会回头修正读数）。workflow 在跑管道前先把这个分支解压到 `archive/`，管道追加本次的文件并据此评分，发布后再推回去。用来以后对照实测评分、校准范围和概率；线上算法以 `method: "v2"` 冻结为基线。行格式和读取函数在 `pipeline/verify/archive.py`，推送由 `scripts/push_archive.sh` 完成；存档失败不影响发布。

数据格式版本是 `schema_version: 2`（字段说明见 `docs/phase2-handoff.md` §2.6 和 `web/lib/types.ts`）。

统一用公制（cm、mm、°C、m、km/h），单位换算在前端做。

## 计算方法

| 步骤 | 做法 | 代码 |
|---|---|---|
| 海拔订正 | 请求时 `elevation=nan` 取格点原始值和格点海拔；用模型自己的气压层温度求该层递减率（限制在 3–9.8°C/km，缺省 6.5），把 2m 气温订正到三个海拔 | `process/lapse.py` |
| 0°C 层、雪线 | 从气压层廓线自上而下找最高的 0°C 层；雪线取湿球温度 +0.5°C 的高度（NWS/NBM 的定义），没有湿度时退化为 0°C 层 − 300m | `process/snowlevel.py` |
| 降水类型 | 雪线以上全是雪，往下 300m 线性过渡到雨；每个海拔分别判断，所以同一场降水可能山顶下雪、山脚下雨 | `process/snowlevel.py` |
| 雪水比 | Kuchera 法（气柱最高温度），上限 25:1；风大时最多再降 35%（风压实） | `process/slr.py` |
| 没有气压层的模型 | 例如 NBM：降水量和 2m 气温用它自己的，雪线和递减率借用其他模型的中位数 | `process/derive.py` |
| 融合（前 10 天） | 按预报时效的经验权重：0–48h 高分辨率模型（HRRR、RRFS、HRDPS、NBM、AROME、ICON-CH）权重大，3–10 天以 ECMWF / NBM / GFS 为主；缺数据的模型自动剔除并重新归一 | `process/blend.py`、`config.py` |
| 集合预报 | ECMWF ENS 51、GEFS 31、GEPS 21、ICON-EPS 40 个成员的逐小时降雪，按山腰海拔请求（Open-Meteo 会把每个成员的气温订正到这个海拔再分雨雪）。按滑雪日汇总后，先按融合的雪水比换算，再乘一个每雪场的系数，使未来 10 天集合平均总量等于融合（全球集合在山区系统性偏干；系数限制在 0.5–2.5）。合并时 ECMWF 算 2 份、其他各 1 份，平均分给各成员 | `ingest/open_meteo_ensemble.py`、`process/ensemble.py` |
| 范围 | 集合成员的加权 10% / 90% 分位（扩到包含点值）；没有集合时退回模型间范围 | `process/blend.py` |
| 信心 | 落在点值 ±50%（至少 ±5 cm）以内的成员比例：≥ 50% 高，≥ 25% 中，否则低；7 天以上最高"中" | `process/blend.py` |
| 第 11–16 天 | 不发布单一数值，只发布分位数和"至少 2.5 cm / 15 cm"的概率（达到阈值的成员占比） | `publish/build.py` |
| 第 3–5 周 | 35 天的 GEFS 和 GEPS 的周累计降雪（山腰）：中位数、10–90% 和 ≥15 / 30 / 60 cm 的概率 | `publish/build.py` |
| 夜间 / 白天 | 滑雪日 D：夜间 = 前一天 16:00 → 当天 08:00，白天 = 08:00 → 16:00（雪场当地时间） | `process/aggregate.py` |

### 回测示例：2024 年 3 月内华达山暴雪

`tests/test_backtest.py` 用真实历史数据（`scripts/make_backtest_fixture.py` 可重新生成）：SNOTEL 784「Palisades Tahoe」（2441m）2024-02-28 至 03-05，对比存档的 GFS / ECMWF / HRRR 预报。

| | 液态降水 | 本管道算出的降雪（2441m） | 平均雪水比 |
|---|---|---|---|
| SNOTEL 实测 | 208 mm | — | — |
| ECMWF | 206 mm | 350 cm | 17.0 |
| HRRR | 268 mm | 335 cm | 12.5 |
| GFS | 317 mm | 401 cm | 12.6 |

这个回测能说明和不能说明的事：

- 液态降水：ECMWF 与雨量计一致，HRRR、GFS 偏多 30–50%。暴风雪里雨量计会漏测，所以真实值应高于 208mm。
- 降水类型：三个模型在站点全程判为雪，山顶比山腰冷、山腰比山脚冷，格点海拔差 220m 的三个模型订正后气温相差不到 1.5°C。
- 雪水比**无法**用这个站验证：风暴期间雪深传感器不可靠（3 月 2 日还在下大雪，读数反而降了 23cm）。纯 Kuchera 会把这场雪算成 4–5 米，所以加了风压实修正；它的系数是经验值，要等第 4 阶段用雪场官方雪报来校准。

## 本地运行

```bash
# 数据管道（Python 3.11+）
pip install -r requirements.txt
python -m pytest -q                              # 单元测试 + 回测 + 预算检查
python -m pipeline.run --out site/data/v1 --mode full --previous none   # 全部雪场全量（约 10 分钟，约 4,500 次加权调用）
python -m pipeline.run --resorts alta,vail --mode full --previous none  # 只跑部分雪场
python -m pipeline.run --out site/data/v1        # 按计划：只刷新到期的雪场，其余从线上上一版带过
python -m pipeline.run --out site/data/v1 --archive archive   # 同时把本次发布的预报写进 archive/forecasts/
python -m pipeline.run --out site/data/v1 --stations none     # 不拉 SNOTEL 实测（默认读 data/stations.yaml）
python scripts/match_stations.py                 # 重新给雪场配 SNOTEL 站，写 data/stations.yaml

# 前端（Node 20+）
cd web && npm install
NEXT_PUBLIC_DATA_BASE=/snow/data/v1 npm run build   # 本地数据；不设则读线上 GitHub Pages
```

要在本机看完整效果，把 `web/out/` 复制到主站仓库的 `aiverse/snow/`（本地数据再复制 `site/data` 到 `aiverse/snow/data`），启动主站 `PORT=10081 python server.py`，打开 `http://localhost:10081/snow/`。

## 如何加雪场

`data/resorts.yaml` 分两部分：标记行以上是第一阶段的 10 个雪场，手工维护；标记行以下由 `scripts/build_resorts.py` 根据 `data/resort_seed.txt` 生成，不要直接改。

1. 在 `data/resort_seed.txt` 加一行（格式在文件头部）：名称、通行证、大致位置、公开的山脚 / 山顶海拔。多山头目的地每个山头一行，共用 `destination`。
2. `python scripts/build_resorts.py`：查 OSM `landuse=winter_sports` 多边形定坐标（没有就用索道站点的中心），查维基信息框和雪场公布的海拔，再用 OSM 索道站点在高程模型上的海拔核对；来源不一致或靠猜的标 `needs_review: true` 并在 `notes` 写原因。网络结果缓存在 `raw/build_resorts/`，报告在 `raw/build_resorts/report.md`。
3. 新区域要在 `regions:` 里加一行。想让它每 6 小时更新就加进 `data/featured.yaml`（`tests/test_budget.py` 会检查额度）。
4. `python -m pytest -q`（会校验整个雪场库和额度），然后提交推送：数据在下一次定时运行时自动包含新雪场。
5. 运行 `scripts/deploy_shell.sh` 并推送主站仓库，新雪场的页面才会出现（外壳里有每个雪场的静态路由）。

新国家需要区域模型时，在 `pipeline/config.py` 的 `MODELS` 里加一条 `ModelSpec` 并在 `BLEND_WEIGHTS` 里给权重；每个雪场最多 8 个模型（模型图只有 8 个固定颜色），standard 档用哪个区域模型在 `_regional_pick()` 里定。

## 部署

| 什么 | 怎么更新 |
|---|---|
| 预报数据 | 全自动：`.github/workflows/forecast.yml` 每天 02:37 / 08:37 / 14:37 / 20:37 UTC 运行，也可在 Actions 页手动触发（手动触发也只刷新到期的雪场）。失败时不发布（线上保留上一版）并自动开一个 issue；少于 90% 的雪场有数据时也不发布 |
| 页面外壳 | `scripts/deploy_shell.sh` 构建并复制到 `../tokenfly/aiverse/snow/`，然后在主站仓库里提交推送，Render 自动部署 |
| 主站路由 | 主站仓库的 `snow_site.py`（`register_snow(app)`）：`/snow` → 302 `/snow/`，目录自动找 `index.html`，带路径穿越校验 |

PWA 的 manifest 和 service worker 的 scope 都是 `/snow/`：页面走网络优先（离线时用缓存），带哈希的静态资源走缓存优先，预报 JSON 走 stale-while-revalidate。

## 数据来源与署名

- [Open-Meteo](https://open-meteo.com/)（CC BY 4.0）：ECMWF IFS / AIFS、NOAA GFS / NBM / HRRR / RRFS、DWD ICON、加拿大 GEM / HRDPS、JMA、Météo-France AROME / ARPEGE、MeteoSwiss ICON-CH、英国气象局全球模型、CMA GRAPES；集合预报 ECMWF ENS、GEFS、GEPS、ICON-EPS。免费档仅限非商用：600 次/分钟、5,000 次/小时、10,000 次/天；超过 10 个变量或 14 天按比例多计，集合的每个成员算一个变量。
- 底图：[OpenFreeMap](https://openfreemap.org/)（免密钥），© OpenStreetMap 贡献者。
- 实测与回测：[USDA NRCS SNOTEL](https://www.nrcs.usda.gov/wps/portal/wcc/home/)，AWDB REST API（公有领域）。
- 雪场坐标与索道：© OpenStreetMap 贡献者（ODbL），经 Overpass API；海拔：维基百科与雪场官网，用 Mapzen 地形数据（经 Open Topo Data）核对。
- 雪场名单：ikonpass.com 与 epicpass.com 的 2026-27 通行证页面（2026-11-11 核对）。

页面的「数据与方法」页会显示每次运行的模型状态和来源。

## 已知限制

- 各海拔的降水量相同，没有做地形增幅；模型格点降水本身在陡峭地形上会偏少或偏多。
- 雪水比的风修正、融合权重都是经验值。回测显示学出来的权重对融合没有显著改善，所以先不换；按雪场的总量偏差订正（A5）等存档积累几周、用 9 公里 ECMWF 的实际评分再学（回测的系数是 0.25° 版本的）。
- 集合预报只有山腰一个海拔；山脚 / 山顶的分位数按融合里的海拔比例缩放。订正系数是"让集合平均等于融合"，不是用实测校准的；范围和概率的校准（A7）要等存档积累一个月（约 2026-12 中）。
- standard 档的雪场一天只更新一次，集合只有 GEFS（31 个成员），范围比 featured 雪场粗。
- 回测（美国西部 29 个 SNOTEL 站、两个雪季）：模型间范围只覆盖 34%–48% 的实际降水，集合范围的覆盖率要等存档积累（`/accuracy` 页会显示）；雪水比用 SNOTEL 验证不了，是降雪英寸数最大的误差来源。
- 实测只有美国西部 34 个有 SNOTEL 站的雪场。测站的新雪是下限（新雪会压实、风会吹走），雨量计在大风中少测；美国东部、加拿大、欧洲、日本还没有实测来源。
- "去哪滑"页的概率是集合预报自己的，还没用实测校准；粉雪分的系数是初始值。
- 46 个雪场标了 `needs_review`（坐标或海拔来源不一致、靠猜），清单见 `docs/phase2-handoff.md` §5。
- Open-Meteo 文档显示 HRRR、ICON Global 等标有停用日期（未能二次确认）；模型缺数据时会被自动剔除并在页面标注。

## 路线图

1. ✅ MVP：10 个雪场、多模型抓取、订正 + 雪线 + 雪水比、详情页、收藏、自动更新
2. ✅ 集合预报（ECMWF ENS、GEFS、GEPS、ICON-EPS）+ 概率与信心；地图和排行榜；第 3–5 周展望；Ikon / Epic 全部雪场；欧洲区域模型；分档更新
3. 准确率与决策器（进行中）
   - ✅ standard 档加 ICON、GEM；跳过的定时运行由下一次补上
   - ✅ 预报存档（`archive` 分支）
   - ✅ `planner.json` + 粉雪分；"去哪滑"页（未来 5 天排雪场，更远只排日子和地区；可分享链接）
   - ✅ SNOTEL 实测接入（美国西部 34 个雪场，详情页"附近实测"）
   - ✅ 评分（`verification.json`，每次运行滚动更新；样本要积累几周）和成绩单页 `/accuracy`（误差随提前量、对比 NBM / ECMWF / GFS、概率可靠性、逐日预报对比实测、复算链接）
   - ✅ ECMWF 换成 9 公里版本（廓线取 0.25°）
   - 范围和概率校准（等存档积累一个月）→ 总量偏差订正 → 准确率页面
   - ✅ 日历订阅提醒（`.ics`，不需要账号）
   - ✅ 预报趋势：每个滑雪日"比昨天的预报多 / 少多少"
   - 通行证分产品与限制日期、路网车程表
4. Claude 每日雪报（中 / 英，结构化 JSON + 数值校验，读 NWS AFD）
5. 登录与跨设备同步（Supabase）、邮件粉雪警报、月 / 季展望、数据迁移到 Cloudflare R2
