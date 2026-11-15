# 雪报 第二阶段：架构、现状与交接计划

> 写于 2026-11-14。给接手的 agent / 开发者看的：读完这一份就能知道第二阶段要做什么、已经做到哪、剩下的怎么拆、每一块做完的标准是什么。
>
> 仓库：`/Users/chenyangcui/Documents/code/snow`（GitHub `TokenFlyAI/snow`）。先读仓库根目录的 `README.md`（第一阶段的架构、数据布局和方法），本文只写第二阶段新增和改动的部分。

---

## 0. 一页摘要（2026-11-14 晚更新）

| | 状态 |
|---|---|
| 集合预报 + 分位数 / 概率 / 信心 / 第 3–5 周展望 | ✅ 完成 |
| 雪场库：Ikon + Epic 2026-27 全部雪场 | ✅ 229 个预报点，44 个 `needs_review`（§5） |
| 欧洲区域模型 | ✅ Météo-France、MeteoSwiss、UKMO；欧洲 4 个重点雪场使用 |
| API 分档与预算 | ✅ 估算每天 6,464 次（28 个重点雪场）；限速器每分钟 480、每小时 4,800 |
| 全量本地运行（229 点，`--mode full`） | ✅ 229/229，实测 **4,451** 次加权调用，与估算一致；所有模型和集合 100% 成功 |
| 按计划运行（`--previous` 沿用上一版） | ✅ 刷新 28、沿用 201，实测 722 次 |
| 前端 | ✅ typecheck + build 通过；已在浏览器里按手机宽度、深 / 浅色检查雪场页、地图、排行、方法页 |
| `python -m pytest -q` | ✅ 103 passed；CI 两项通过 |
| PR | [TokenFlyAI/snow#1](https://github.com/TokenFlyAI/snow/pull/1) |
| GitHub `forecast` workflow | 见 PR 合并后的运行 |
| 部署主站外壳（tokenfly） | ❌ 未做，**必须先给用户看结果、拿到同意再推送** |

全量运行的观察：订正系数中位数 1.0，22/229 顶到上下限（多为只有 GEFS 的欧洲 standard 雪场，全球集合在阿尔卑斯严重偏干，例如 Veysonnaz 融合 91 cm vs GEFS 17 cm）；单个雪场文档约 29 KB，全部约 6.9 MB，`ens/` 约 1.2 MB，`resorts.json` 约 360 KB。

---

## 1. 目标与完成标准（来自用户的原始要求）

1. **集合预报**：接 Open-Meteo Ensemble API；每个雪场发布日降雪的 10/50/90 百分位；用集合离散度替换原来"模型间范围"和 `confidence` 逻辑；第 10 天以后只发布概率（≥2.5 cm、≥15 cm），不给单一数值；第 3–5 周按周给概率式展望。
2. **全部雪场**：Ikon 和 Epic 2026-27 全球所有雪场；坐标取 OSM `landuse=winter_sports` 中心，海拔取雪场官网或维基；每条写来源；两个来源不一致或靠猜的标 `needs_review: true` 并列给用户；多山头目的地拆成多个预报点、共享 `destination`；`pipeline/config.py` 加欧洲区域模型。
3. **API 预算**：免费档每天 10,000 次加权调用；`data/featured.yaml` 里的重点雪场每 6 小时全模型，其余每天一次精简模型集；实测 `manifest.json` 里的 `api_usage`，每天总量 < 8,000。
4. **前端**：逐日图加集合区间带；地区总览页（MapLibre 地图，按未来 N 天降雪上色）；3 / 7 / 16 天排行榜。遵守 `web/components/charts/` 的图表规则：一个图一个 y 轴、每个模型固定颜色、两个以上系列要有图例、提供表格视图。

**完成的定义**：`python -m pytest -q` 通过且有百分位和概率的新单测；`python -m pipeline.run` 对全部雪场跑完且在预算内；GitHub 上 `forecast` workflow 成功；页面在真实浏览器里以手机宽度、深色模式截图检查过。

**硬约束**：只用免费开放数据；不加任何需要新账号或密钥的东西（Supabase、R2、邮件、Anthropic key 都属于后续阶段）；推送 `tokenfly` 仓库会重新部署用户主站，**必须先给用户看并得到同意**；本地跑 tokenfly 服务会改动它仓库里被跟踪的 `stats.db` 和 `games/data/games.json`，提交前要还原。用户读中文。

---

## 2. 整体架构（第二阶段之后）

```
TokenFlyAI/snow（公开）
├─ data/
│   ├─ resorts.yaml          雪场库：上半部分 10 个手工维护，标记行以下由脚本生成
│   ├─ resort_seed.txt       ← 新：219 个雪场的种子表（名称/通行证/大致位置/公开海拔）
│   └─ featured.yaml         ← 新：重点雪场（每 6 小时全模型）
├─ scripts/
│   ├─ build_resorts.py      ← 新：种子表 → OSM + 维基 + DEM 核对 → resorts.yaml
│   └─ deploy_shell.sh       构建前端并复制到 ../tokenfly/aiverse/snow/
├─ pipeline/
│   ├─ config.py             模型目录、集合目录、分档、预算估算、刷新时段
│   ├─ state.py              ← 新：读取上一版已发布数据（URL 或目录）
│   ├─ run.py                计划 → 抓取 → 计算 → 发布（改写）
│   ├─ ingest/open_meteo.py           确定性模型 + 限速器 + 用量记录（改）
│   ├─ ingest/open_meteo_ensemble.py  ← 新：集合 API
│   ├─ process/ensemble.py            ← 新：成员日总量、合并、订正、分位数、概率
│   ├─ process/blend.py               融合；信心改为集合一致度（改）
│   └─ publish/build.py               JSON 组装，schema v2（改）
└─ web/                      Next.js 静态导出（新增 /map、/rank 页）

GitHub Actions forecast.yml（每天 02:37 / 08:37 / 14:37 / 20:37 UTC）
  └─ python -m pipeline.run --out site/data/v1
       ├─ 读上一版：https://tokenflyai.github.io/snow/data/v1/{resorts.json, resort/*.json, ens/*.json}
       ├─ 只刷新"到期"的雪场，其余原样带过去
       └─ 发布完整的一套到 GitHub Pages
浏览器 tokenfly.ai/snow/ ──fetch──▶ tokenflyai.github.io/snow/data/v1/
```

### 2.1 为什么要"读上一版"

GitHub Pages 每次部署是整体替换。分档后大多数雪场一天只刷新一次，所以每次运行先拉上一版已发布的文件：不到期的雪场直接复制旧文档；集合成员的日总量缓存在 `ens/{id}.json`，在两次集合刷新之间复用。上一版读不到（404、网络错、schema 不是 2）时该雪场视为"新"，当次全量刷新。**注意**：第一阶段线上是 schema v1，会被全部拒绝，所以第二阶段第一次上线等于一次全量运行（见 §6 风险 1）。

### 2.2 一次运行的流程（`pipeline/run.py`）

1. `plan()`：对每个雪场决定 `det`（抓确定性模型、重建文档）和 `ens`（抓集合）。
   - `featured`：每次都 `det`；集合在它所在时段刷新。
   - `standard`：只在自己所在时段刷新（`det` + `ens`）。
   - 时段：`config.refresh_slot(lon)`，让刷新落在当地早晨之前：欧洲（经度 −30…60）02 UTC，北美东部和南美（−100…−30）08 UTC，北美西部（< −100）14 UTC，亚洲 / 大洋洲 20 UTC。`current_slot(hour)` 把延迟的 cron 也归到对应时段。
   - 超过 `STALE_AFTER_H = 28` 小时的强制刷新；到期但距上次不足 `FRESH_WITHIN_H = 5` 小时的不重复刷新；分档变了、上一版没有的，都刷新。
   - `--mode full` 全部刷新；`--mode featured` 只刷重点雪场（缺的仍会补）。
2. 抓取：每个模型一次请求带多个坐标（确定性 50 个一批，集合 25 个一批）。所有请求经过 `RateLimiter`（每分钟 480 加权调用，免费档是 600）。429 时至少等 61 秒重试。
3. 每个雪场：确定性模型 → `derive`（海拔订正、雪线、雪水比，第一阶段代码未改）→ 融合 → 和集合合并 → `build_resort`。
4. 写 `ens/{id}.json`、`resort/{id}.json`，再写 `resorts.json`，最后写 `manifest.json`（存在即表示本次完整）。
5. 不发布的条件：有确定性任务但可用模型 < 2；或拿到文档的雪场 < 90%。单个雪场没数据时保留上一版文档。

### 2.3 模型

**确定性**（`config.MODELS`，按 `countries` 过滤）：

| id | 标签 | 适用 |
|---|---|---|
| ecmwf_ifs025 / ecmwf_aifs025_single / gfs_global / icon_seamless / gem_global | 全球 | 全部 |
| ncep_nbm_conus / ncep_hrrr_conus / ncep_rrfs_conus | 美国本土 | US（不含 AK、HI） |
| gem_hrdps_continental | HRDPS | CA |
| jma_seamless | JMA | JP、KR、CN |
| meteofrance_seamless | Météo-France（AROME 1.3 km / ARPEGE） | FR、CH、IT、AT、AD |
| meteoswiss_icon_seamless | MeteoSwiss ICON-CH1/CH2 | FR、CH、IT、AT（没有气压层，用其他模型的中位廓线） |
| ukmo_seamless | UKMO 10 km | 北美以外 |
| cma_grapes_global | CMA | CN |

- `icon_seamless` 在阿尔卑斯已经内嵌 ICON-D2（2 km）和 ICON-EU，所以没有单独加。
- `italia_meteo_arpae_icon_2i` 试过、可用，但会让意大利雪场有 9 个模型，超过模型图的 8 个固定颜色，已去掉。`tests/test_budget.py` 会检查每个雪场 ≤ 8 个模型。
- 探测过不可用的：`kma_seamless`、`bom_access_global`（返回 0 小时）、`arpae_cosmo_seamless`（已停用）、`geosphere_arome_austria`（无数据）。
- `standard` 只用 3 个：ECMWF IFS + GFS + 一个区域模型（`config._regional_pick`：美国本土 NBM，加拿大 HRDPS，日中韩 JMA，欧洲 ICON，其他 UKMO，阿拉斯加 ICON）。
- 融合权重 `BLEND_WEIGHTS` 加了新模型（经验值，第 4 阶段用验证数据替换）。

**集合**（`config.ENSEMBLES`，2026-11 在线核实过，字段名形如 `snowfall_member01`，控制成员是不带后缀的 `snowfall`）：

| id | 标签 | 成员（含控制） | 请求天数 | 合并权重 | 档 |
|---|---|---|---|---|---|
| ecmwf_ifs025 | ECMWF ENS | 51 | 15 | 2.0 | featured |
| gfs05 | GEFS | 31 | 35 | 1.0 | featured + standard |
| gem_global | GEPS | 21 | 35 | 1.0 | featured |
| icon_seamless | ICON-EPS | 40 | 8 | 1.0 | featured |

### 2.4 集合方法（`pipeline/process/ensemble.py`）

- **只请求一个变量**：逐小时 `snowfall`，`elevation` 设为雪场山腰海拔。实测 Open-Meteo 会把每个成员的气温订正到这个海拔再分雨雪，所以每个成员自带雨雪判断；数量按固定 7:1（每 mm 水 0.7 cm 雪）。请求 `elevation=nan` 时 ICON-EPS 会用格点海拔导致降雪偏少 3 倍，所以必须传海拔。
- **两段式**：
  1. `raw_document()` 把每个成员的逐小时降雪汇总成"滑雪日"（前一天 16:00 → 当天 16:00 当地时间，与第一阶段一致；一天至少 80% 小时有值）总量，存 `ens/{id}.json`（未订正、7:1、山腰）。
  2. 每次生成文档时 `Pool.from_raw()` 按日期对齐（旧缓存会自动平移），再 `calibrate()`：先乘以融合给出的当天雪水比 / 7，再乘一个每雪场一个的系数，使未来 10 天集合平均总量等于融合总量（全球集合分辨率低，山区系统性偏干）。系数限制在 0.5–2.5；少于 3 天或总量 < 5 cm 时不订正（系数 1）。
- **合并**：所有成员放一起，每个成员权重 = 模型权重 / 该模型成员数（ECMWF 整体算 2 份）。
- **分位数** `weighted_quantiles()`：与 `blend.weighted_quantile` 同一定义（加权中点 CDF 线性插值）；NaN 和零权重成员忽略。
- **概率** `prob_at_least()`：达到阈值（含等于）的成员权重占比，缺值成员不投票。日阈值 `DAY_THRESHOLDS_CM = (2.5, 15)`，周阈值 `WEEK_THRESHOLDS_CM = (15, 30, 60)`。少于 `MIN_MEMBERS = 8` 不发布。
- **三个海拔**：集合只有山腰；山脚 / 山顶按融合里该日（或整段）的海拔比例缩放（`level_ratio`，0–2.5）。
- **窗口总量** `window_totals()`：成员覆盖 ≥ 85% 的天数即可，缺的天用自身均值补（ECMWF 只有 15 天也能进 16 天总量）；今天的滑雪日在欧洲 / 亚洲往往在运行前就开始了，没有成员覆盖，用融合值补。

### 2.5 范围与信心（`pipeline/process/blend.py`）

- `daily_range()`：有集合用集合 10–90%，没有就退回模型间加权 10–90%；都会扩到包含发布的点值。`range_source` 字段标明来源。
- `ensemble_agreement()`：落在点值 ±50%（至少 ±5 cm）以内的成员权重占比。
- `ensemble_confidence()`：≥ 0.5 高，≥ 0.25 中，否则低；第 7 天起最高为中。（阈值是在 Alta 真实数据上看过后定的，第一次试 0.60 / 0.35 几乎全是"低"。）
- `model_spread_confidence()`：没有集合时的旧逻辑（第 6 天起最高为中）。

### 2.6 发布数据 schema v2（`SCHEMA_VERSION = 2`）

`resort/{id}.json`：

- `resort`：元数据 + `tier`（`featured` / `standard`）。
- `ensemble`：`{generated_at, level:"mid", elevation_m, models:[{id,label,members,horizon_days}], calibration:{factor, slr_default, days, blend_cm, ensemble_cm}}`，无集合时为 `null`。
- `daily`：最多 16 条。
  - `lead_days` 0–9：`kind:"point"`，第一阶段的全部字段 + `snow_low_cm/snow_high_cm`（见上）+ `range_source` + `ens`（`{p10,p50,p90,mean: ByLevel, prob:{"2.5":ByLevel,"15":ByLevel}, n_members, agreement}`，可能为 `null`）。
  - `lead_days` 10–15：`kind:"prob"`，只有 `date / lead_days / ens`，**没有** `snow_cm`。
- `outlook`：第 3/4/5 周（第 n 周 = 第 7(n−1) 到 7n−1 天），`{week,start,end,p10_cm,p50_cm,p90_cm,mean_cm,prob:{"15","30","60"},n_members,models}`，山腰。
- `summary`：保留 `snow_24h_cm / snow_72h_cm / snow_7d_cm`（按小时累计）；新增 `totals: {3d,7d,16d: {cm, low_cm, high_cm, days, complete}}`（按滑雪日，16 天的后 6 天用集合均值）；`snow_16d_cm` 现在等于 `totals["16d"].cm`；`daily_mid_cm` 只有前 10 天；`next_snow` 只在前 10 天找。
- `by_model_daily_cm`：只有前 10 天。

`resorts.json` 每个雪场新增：`tier, generated_at, ensemble_at, n_members, outlook（精简）`；`dates` 只有点值日。

`manifest.json` 新增：`run`（模式、时段、刷新 / 带过 / 失败的数量）、`ensembles`（各集合状态）、`api_usage.by_kind`（deterministic / ensemble）、`api_usage.daily_estimate`（按 4 次运行估算的每日总量）、`daily_limit`、`daily_target`。

`ens/{id}.json`：原始成员日总量缓存（见 §2.4），前端不读。

### 2.7 API 预算

计费规则（读过 Open-Meteo 源码 `ForecastapiController.swift` 确认）：`max(1, 变量数/10) × max(1, 天数/14) × 坐标数`；集合里**每个成员都算一个变量**。

- 确定性：29 个逐小时变量，`FORECAST_DAYS` 从 16 降到 12（+1 天过去 = 13 天，仍在一个 14 天单位内）→ 每模型每点 2.9。点值只到第 10 天，更远的由集合负责。
- 集合每点：ECMWF 5.46、GEFS 7.75、GEPS 5.25、ICON-EPS 4.0。
- 每点每天：featured 美国约 8×2.9×4 + 22.5 ≈ 115；standard 3×2.9 + 7.75 ≈ 16.5。
- **当前配置估算（229 点、24 个 featured）**：featured 确定性 2,158 + standard 确定性 1,784 + 集合 2,128 = **6,069 / 天**。`tests/test_budget.py` 在超过 8,000 时失败。
- 一次全量运行（`--mode full`）约 **4,450**。

### 2.8 雪场库（`data/resort_seed.txt` → `scripts/build_resorts.py` → `data/resorts.yaml`）

- 名单于 2026-11-11 对照 `ikonpass.com/en/shop-passes/ikon-pass`（26/27：18 个不限次、其余 7 天、14 个 Bonus 山 2 天）和 `epicpass.com/passes/epic-pass.aspx` + `/regions/europe.aspx`（2026/27）。
- 种子表一行一个预报点：`id | name | name_zh | destination | pass:tier | country | state | region | lat | lon | base | summit | options`。海拔后加 `?` 表示粗估；options：`tz=`、`r=`（搜索半径 km）、`osm=`（名称提示）、`wiki=`（条目名）、`nowiki`。
- 脚本对每个点：Overpass 查 `landuse=winter_sports`（按名称匹配，否则距离最近且 ≤3 km；同一多边形被多个点共用时只给名称匹配的）→ 坐标取多边形边界框中心（Overpass 带 `bb` 时不返回 `center`，所以自己算，与 Overpass 的 center 定义相同）；没有多边形时用索道站点质心；再查索道站点在 Mapzen DEM（Open Topo Data）上的最低 / 最高海拔做核对；海拔优先维基信息框，否则用种子表。
- 标 `needs_review` 的规则：维基与种子相差 > 60 m；山脚与最低索道站相差 > 150 m；山顶比最高索道站高 > 250 m 或低 > 100 m；坐标或海拔靠猜。
- 网络结果缓存在 `raw/build_resorts/`（已 gitignore），`--offline` 只用缓存重建；报告在 `raw/build_resorts/report.md`。
- 10 个第一阶段雪场在标记行之上，手工维护，脚本不碰。
- 统计：Ikon 7 天 97、不限 19、2 天 14；Epic 不限 44、5 天 29、7 天 21、3 天 5。拆分的目的地 22 个（如 dolomiti-superski 12 点、hakuba-valley 10 点、aspen-snowmass 4 点、niseko-united 4 点、skibig3 3 点、les-3-vallees 6 点）。区域从 9 个扩到 25 个（`regions:`）。

### 2.9 前端（`web/`）

| 文件 | 内容 | 状态 |
|---|---|---|
| `lib/types.ts` | schema v2 类型：`DayEntry = Daily \| ProbDay`、`EnsDay`、`OutlookWeek`、`EnsembleInfo`、`WindowTotal`、manifest 新字段 | 写完 |
| `lib/i18n.ts` | 新文案（中英），`fmtRange`、`fmtProb`（<5% / >95%），`tierKey` 支持 3day | 写完 |
| `lib/units.ts` | `fmtThreshold`（阈值按 cm 定义，英制显示整数英寸） | 写完 |
| `lib/windows.ts` | 3 / 7 / 16 天窗口取值（含集合范围） | 写完 |
| `components/charts/DailyChart.tsx` | 前 10 天夜间 + 白天堆叠柱；16 天集合 10–90% 灰带（不可见下边线 + 堆叠差值面积）+ 虚线中位数；第 11 天起 markArea 标"只给概率"；tooltip 显示概率 | 写完，**没看过效果** |
| `components/Outlook.tsx` | `ProbDays`（第 11–16 天概率表）、`OutlookWeeks`（第 3–5 周卡片，单色细条 + 数字） | 写完 |
| `components/charts/ModelChart.tsx` | 只画点值日；新模型的固定颜色槽（区域不重叠，可共享槽） | 写完 |
| `app/resort/[id]/ResortClient.tsx` | 分档说明、16 天总量下方显示范围、逐日表只列点值日 + 信心旁显示一致度、概率表、集合说明、展望区块 | 写完 |
| `app/rank/page.tsx` | 排行：3/7/16 天、海拔、Ikon/Epic、地区筛选；每行蓝色条 + 灰色 10–90% 须线；默认 40 行可展开 | 写完 |
| `components/map/SnowMap.tsx`、`app/map/page.tsx` | MapLibre（`maplibre-gl@^4.7.1` 已装）+ OpenFreeMap 免密钥底图（亮 `positron` / 暗 `dark`）；圆点按窗口总量分 6 级（灰 = 几乎没有，5 级单色蓝，暗色模式反向）；点击选中显示 `ResortCard`；地区下拉缩放；图例；底图失败时提示，下方列表照常可用 | 写完，**有类型错误**，没看过 |
| `components/Header.tsx` | 导航：我的雪场 / 地图 / 排行 / 全部雪场 / 方法（可横向滚动） | 写完 |
| `app/page.tsx` | 首页排行截到前 10 + "查看完整排行" | 写完 |
| `app/about/page.tsx` | 方法说明重写（集合、信心、第 11 天以后、更新频率）；集合状态；API 额度 | 写完 |
| `public/sw.js` | 缓存版本 v2，预缓存加 `map/`、`rank/` | 写完 |

---

## 3. 剩余工作：拆成可以分给不同人的工作包

依赖关系：

```
WP1 前端类型修复 + 构建 ──┐
                         ├─▶ WP2 浏览器验证（需要 WP4 的本地数据，或先用小规模运行的数据）
WP4 全量本地运行 ─────────┘
WP3 预算加固 + workflow + README ─┐
                                 ├─▶ WP6 提交 / PR / CI / 触发 forecast ─▶ WP7 部署主站（需用户同意）
WP1、WP2、WP4 ───────────────────┘
WP5 雪场数据复核 —— 可随时并行，结果在下一次 forecast 运行时自动生效（但新增 / 删除雪场需要 WP7 重新部署外壳）
```

不同工作包改的文件不重叠：WP1/WP2 → `web/`；WP3 → `pipeline/config.py`、`pipeline/run.py`、`.github/workflows/`、`README.md`、`tests/test_run_plan.py`；WP5 → `data/resort_seed.txt`、`data/resorts.yaml`、`scripts/build_resorts.py`。WP4 只读代码、只写 `site/`（gitignore）。

### WP1 前端类型修复与构建（✅ 已完成）

- 问题：`npx tsc --noEmit` 在 `web/components/map/SnowMap.tsx` 第 67、77、83 行报错：`latest.current.theme` 被推断成 `string`，不能用来索引 `STYLE` / `SNOW_RAMP`。修法：`type Theme = "light" | "dark"`，`const theme: Theme = ...`，并给 `latest` 的 `useRef` 标类型。
- 然后 `cd web && npm run typecheck && NEXT_PUBLIC_DATA_BASE=/snow/data/v1 npm run build`。
- 检查：构建产物里有 229 个 `resort/*/index.html`、`map/`、`rank/`；MapLibre 是动态 import，不应进首页包（看 `next build` 输出的首屏 JS 大小）。
- 完成标准：typecheck、build 都通过。

### WP2 浏览器验证（✅ 已完成，修了阈值顺序、模型图负轴、地图版权框、深色控件、"下一场雪"指向已结束的滑雪日）

- 数据：用 WP4 生成的 `site/data/v1`；WP4 没好时先跑小规模：`python -m pipeline.run --out site/data/v1 --resorts alta,kirkwood,niseko-hirafu,zermatt,val-thorens,whistler-blackcomb --mode full --previous none`（约 150 次加权调用）。
- 本地预览：README「本地运行」一节的方法（`web/out/` 复制到 tokenfly 的 `aiverse/snow/`，数据复制到 `aiverse/snow/data`，`PORT=10081 python server.py`，打开 `http://localhost:10081/snow/`）。**跑完把 tokenfly 的 `stats.db`、`games/data/games.json` 用 `git checkout --` 还原，`aiverse/snow/` 也还原**（那是 WP7 的事）。也可以直接对 `web/out` 起一个静态服务器并把 basePath 对上。
- 逐页检查（375 宽，深色和浅色各一遍，中文和英文各看一次）：
  - 雪场详情：逐日图灰带和柱子不打架、第 11–16 天只有灰带和"只给概率"标注、图例 4 项、y 轴只有一个；tooltip；概率表；第 3–5 周卡片；模型图颜色固定；英制单位切换。
  - 地图：底图加载、圆点颜色与图例一致、深色模式底图切换后图层还在（`style.load` 重新加图层）、点击弹出卡片、地区下拉缩放、放大后有名字和数值标签。
  - 排行：3/7/16 切换、须线在条上、筛选、"显示全部"。
  - 首页、方法页（集合状态、API 额度）。
- 配色：地图的蓝色分级是从 dataviz 参考色板取的，按 dataviz 规范应跑一次 `validate_palette.js`（sequential，亮 / 暗两个底色）。
- 交付：截图（手机宽度 + 深色）给用户；发现的问题直接修。
- 完成标准：所有页面无报错（控制台、网络）、截图齐全。

### WP3 预算加固、workflow、README（✅ 已完成：FRESH_WITHIN_H=18、每小时上限、重试只计一次、超时 45 分钟、README 已更新）

1. **首日预算超标风险**（见 §6 风险 1）：建议把 `FRESH_WITHIN_H` 从 5 改到 18——正常的每日刷新在时段到来时已经约 24 小时，不受影响；而全量运行之后 18 小时内各地区时段不会再刷一遍。改后更新 `tests/test_run_plan.py` 的相关用例。
2. `.github/workflows/forecast.yml`：`timeout-minutes: 20` → 40（全量运行约 4,450 加权调用，限速器每分钟 480，至少 9–10 分钟，加上下载上一版 229×2 个文件）。
3. 每小时限额（免费档 5,000/小时）：全量运行接近这个值。`RateLimiter` 只管每分钟，建议加一个每小时上限（例如 4,500），超过就等。
4. `README.md` 更新：第二阶段架构（分档、读上一版、`ens/` 目录、schema v2）、集合方法、预算数字、`build_resorts.py` 用法、加雪场流程改为"改种子表 → 跑脚本"、路线图把第 2 阶段标完成、"已知限制"里"信心只看确定性模型"那条删掉。
5. 完成标准：`pytest` 通过；README 与代码一致。

### WP4 全量本地运行（✅ 已完成：4,451 次）

- 命令：`python -m pipeline.run --out site/data/v1 --mode full --previous none -v`。
- 代价：约 4,450 次加权调用，**算在本机 IP 上**（GitHub Actions 是另一组 IP，不共用额度）。同一天本机不要跑第二次全量。
- 检查：退出码 0；`manifest.json` 的 `api_usage.weighted_calls` 与估算对得上（≈4,450），`daily_estimate.total` ≈ 6,069；`run.failed` 为空；每个模型、集合的 `resorts_ok / resorts_requested`；随便抽几个雪场看 `ensemble.calibration.factor` 分布（大量顶到 2.5 或 0.5 说明订正有问题）；日志里没有 NaN 相关异常。
- 再跑一次 `--mode auto --previous site/data/v1 --out site2/data/v1` 验证"带过"逻辑：只应刷新 featured 和当前时段的地区。
- 完成标准：给出实测用量数字，写进 PR 描述。

### WP5 雪场数据复核（部分完成：修了共用坐标和两个山谷站海拔，剩 44 个 `needs_review`）

逐个处理：改 `data/resort_seed.txt`（`r=`、`osm=`、`wiki=`、海拔）后重跑 `python scripts/build_resorts.py`（有缓存，很快；改了搜索参数的会重新查 Overpass，Overpass 常 502，脚本会自动退避重试）。确认无误但仍被规则标记的，可以在种子表里修正海拔使其通过，或者接受并在报告里说明。需要人看的清单在 §5。另外：

- **通行证天数待核**：Epic 欧洲合作雪场在官网主页只写了"36 个欧洲合作雪场"。种子表里 Verbier 4 Vallées、Zillertal、Silvretta Montafon、Sölden、Saalbach 系列按官网写的 5 天；Ski Arlberg 写 3 天（需住合作酒店）；**Skirama Dolomiti 和 Les 3 Vallées 暂填了 7day，没有核实**，要查 epicpass.com 对应页面。
- **Ikon 奥地利**：26/27 名单只写 "Ischgl, Austria"；种子表把 Kappl、See、Galtür 作为 `ischgl-paznaun` 目的地的点加进来了（destinations 页上它们以子目的地出现），要确认 26/27 是否包含。
- Whistler Blackcomb 仍是一个点（不在用户要求拆分的名单里），可考虑拆成 Whistler / Blackcomb。
- Niseko Hirafu 的坐标仍是第一阶段的估计值；现在有了 hanazono / niseko-village / annupuri 三个新点，其中 hanazono 坐标和海拔都是猜的。
- 完成标准：`needs_review` 剩下的每一条都有说明；`pytest` 通过（`test_resorts.py` 会校验整个库）。

### WP6 提交、PR、CI、触发 forecast

- 分支 `phase2`，按功能分几个提交（集合、雪场库、分档预算、前端）。提交信息结尾按仓库约定加署名行。
- PR → CI（`ci.yml`：pytest + 前端 build + typecheck）通过 → 合并。
- 合并后在 Actions 页手动触发 `forecast`（workflow_dispatch）。注意：线上旧数据是 schema v1，第一次运行会全量刷新（~4,450）。
- 检查 `https://tokenflyai.github.io/snow/data/v1/manifest.json`：`schema_version: 2`、`resort_count: 229`、`api_usage`；之后观察一整天 4 次定时运行的 `api_usage.weighted_calls` 之和 < 8,000。
- 完成标准：workflow 绿；一天的实测用量记录下来。

### WP7 部署页面外壳到主站（必须先得到用户同意）

- `scripts/deploy_shell.sh` → 在 `../tokenfly` 里看 `git status`：只应有 `aiverse/snow/` 的改动；`stats.db`、`games/data/games.json` 若有改动先还原。
- **把 WP2 的截图和线上数据给用户看，拿到明确同意后**再在 tokenfly 提交推送（推送会让 Render 重新部署整个主站）。
- 推送后检查 `https://tokenfly.ai/snow/`、`/snow/map/`、`/snow/rank/`、任意新雪场页。

---

## 4. 常用命令

```bash
cd /Users/chenyangcui/Documents/code/snow
python -m pytest -q                                            # 101 个测试
python -m pipeline.run --out site/data/v1 --resorts alta,zermatt --mode full --previous none -v
python -m pipeline.run --out site/data/v1 --mode full --previous none     # 全量，约 4,450 次加权调用
python scripts/build_resorts.py                                # 重建雪场库（有缓存）
python scripts/build_resorts.py --offline                      # 只用缓存
python scripts/build_resorts.py --only zermatt,verbier         # 调试单个，不写 YAML
cd web && npm run typecheck && NEXT_PUBLIC_DATA_BASE=/snow/data/v1 npm run build
```

估算预算（不调用 API）：

```bash
python -c "from pipeline.config import *; from pipeline.resorts import load_resorts; from pipeline.ingest.open_meteo import hourly_vars; db=load_resorts(); print(estimate_daily_calls(db.resorts, load_featured(), len(hourly_vars())))"
```

---

## 5. 需要人工复核的雪场（写于 46 个时；Grouse、Kitzsteinhorn、Verbier 系列已处理，现 44 个，以 `raw/build_resorts/report.md` 为准）

规则见 §2.8。"DEM" 是 OSM 索道站点在高程模型上的最低–最高海拔，常因混入邻近雪场或山谷缆车而偏离，不一定是我们的数据错。

| id | 原因 |
|---|---|
| whistler-blackcomb | 山顶：维基 2240 m，雪场官方 2284 m；两座山共用一个点 |
| niseko-hirafu | 坐标为估计（OSM 只有整个 Niseko United 的多边形） |
| hanazono | 坐标和海拔都是猜的（OSM 没有可用数据） |
| crystal-ridge | 坐标和海拔都是猜的 |
| aspen-highlands | 维基 2451–3777 m vs 雪场 2451–3559 m（3777 是徒步上去的 Highland Bowl） |
| brighton | 维基 2669–3277 vs 雪场 2668–3200 |
| crystal-mountain | 维基 1192–2137 vs 雪场 1341–2134 |
| summit-at-snoqualmie | 维基 796–1652（含 Alpental）vs 1178；Alpental 已单独成点 |
| cypress-mountain | 维基 826–1440 vs 910–1440 |
| sun-peaks | 维基 1198–2152 vs 1255–2082 |
| snowy-range | 维基 2682–2945 vs 2734–3048 |
| beaver-creek | 维基 2469–3487 vs 2255–3488（2255 是 Avon 谷底） |
| heavenly | 维基 1907–3068 vs 1996–3060 |
| perisher | 维基 1720–2054 vs 1605–2054 |
| telluride | 维基 2659–4008 vs 2659–3831（4008 是徒步顶） |
| pal-arinsal | 维基 1550–2625 vs 1550–2560 |
| grouse-mountain | 公布 274 m（缆车山脚）vs 索道 874 m；滑雪区从 874 m 起，建议改 base |
| shiga-kogen | DEM 1599–1758：只匹配到一个小区域，整个志贺高原 18 个区，可能需拆分或扩大半径 |
| kitzsteinhorn | 公布 911（Kaprun 镇）vs 索道 1973；滑雪区在冰川上，建议 base 改 ~1970 |
| val-thorens | DEM 882–3214：混入了山谷缆车；公布 2300–3230 应是对的 |
| verbier / la-tzoumaz | DEM 489–3297：同一组索道（含 Le Châble 谷底）；需要分开搜索范围 |
| saint-martin-de-belleville | DEM 1386–1796：只找到村子附近的索道 |
| meribel / les-menuires | 公布与 DEM 差 150–250 m，可能混了邻近山谷 |
| megeve / grandvalira / pila / bruson / sedrun / madonna-di-campiglio / st-anton / saalbach-hinterglemm | 山脚比最低索道站高或低 > 150 m（多为镇上的接驳缆车） |
| warth-schroecken | 公布山脚 1270 vs 索道 1480 |
| cortina / val-gardena / san-martino / courmayeur / cervinia / monterosa-ski / see / nakiska / tsugaike / hakuba-norikura | 最高索道站比公布山顶高 100 m 以上（多为混入邻近区域或冰川缆车；Courmayeur 3429 是 Skyway Monte Bianco，不是雪场） |
| alta-badia / arabba-marmolada | 公布山顶比最高索道站高 250 m 以上（Marmolada 3265 是冰川顶，索道 DEM 2902 偏低） |

完整数字在 `raw/build_resorts/report.md`（本地缓存目录，未进 git；重跑脚本可再生成）。

---

## 6. 风险与坑

1. **第一次上线当天可能超 8,000**：线上是 schema v1，第一次运行全部视为新雪场 → 全量 ~4,450；之后各地区时段到来时（距上次 > 5 小时）又会各刷一次 → 当天合计约 9,000（仍 < 10,000 上限）。WP3 第 1 条（`FRESH_WITHIN_H = 18`）可以消除。之后上一版文件读不到（GitHub Pages 抖动）时同理会触发大面积刷新，`Previous.get` 有 3 次重试。
2. **每小时 5,000 限额**：全量运行接近，限速器目前只管每分钟（WP3 第 3 条）。
3. **workflow 超时**：现在 20 分钟，全量运行可能超（WP3 第 2 条）。
4. **Overpass 不稳定**：`build_resorts.py` 期间多次 502，脚本自带退避重试，一次全量构建花了约 1 小时。缓存在 `raw/build_resorts/`，不要删。
5. **MeteoSwiss 没有气压层**：`derive` 会走"无廓线"分支，借用其他模型的中位递减率和雪线（与 NBM 相同的机制），已在真实数据上跑通，但没有单测专门覆盖这个模型。
6. **集合订正系数是经验做法**：只在 Alta（系数 1.48）、Kirkwood、Niseko 三个点上看过。WP4 应看全体分布。
7. **前端没在浏览器里看过**：逐日图的"堆叠差值面积"画法、地图暗色切换后重新加图层、markArea 文案位置，都是最容易出视觉问题的地方。
8. 免费档仅限非商用（Open-Meteo 条款），页面需保留署名（已在 manifest 和方法页）。

---

## 7. 需要用户拍板的事

1. `data/featured.yaml` 的 24 个重点雪场是否合适（目前：加州 5、犹他 3、科罗拉多 6、北落基 2、西北 3、加拿大 2、东部 1、日本 2）。预算还有约 1,900 余量，大约还能再加 15 个美国 featured 雪场。
2. Skirama Dolomiti、Les 3 Vallées 的 Epic 天数，以及 Ikon 是否含 Kappl / See / Galtür（WP5）。
3. Whistler Blackcomb、Shiga Kogen 要不要拆成多个点。
4. WP7 推送主站前的最终确认。

---

## 8. 本次已验证过的事实（避免重复踩坑）

- Ensemble API 四个模型 id、成员数、时效（2026-11-11 实测）：ECMWF 51 成员到第 15 天、GEFS 31 成员到第 34–35 天、GEPS 21 成员到第 35 天、ICON-EPS 40 成员到第 8 天。
- 集合的 `snowfall` 会按请求的 `elevation` 订正：1200 m vs 2325 m 在 Tahoe 差几十倍；`elevation=nan` 时 ICON-EPS 用格点海拔，降雪少 3 倍。
- 计费公式与成员计数：Open-Meteo 源码 `Sources/App/Controllers/ForecastapiController.swift` 第 ~308 行。
- 区域模型可用性：`meteofrance_seamless`（115 h）、`meteoswiss_icon_seamless`（133 h，无气压层）、`icon_d2`（64 h）、`icon_eu`（133 h）、`ukmo_seamless`（169 h，全球）、`cma_grapes_global`（127 h）、`italia_meteo_arpae_icon_2i`（85 h，意大利）；`kma_seamless`、`bom_access_global` 返回 0 小时；`arpae_cosmo_seamless` 已停用。
- Overpass：`out center bb` 不返回 `center`，要自己用 `bounds` 算。
- 免密钥底图：`https://tiles.openfreemap.org/styles/{positron,dark,liberty,bright}`，字体 `Noto Sans Regular`。
- 3 个雪场真实运行（2026-11-11）：全量 105 次加权调用（确定性 52、集合 53）；`--mode featured --previous <上次输出>` 43 次，未到期雪场的文档逐字节相同地被带过。
