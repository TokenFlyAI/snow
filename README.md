# 雪报 Snow

多模型融合的滑雪场降雪预报，页面在 **https://tokenfly.ai/snow/**（PWA，可安装到手机）。

- 每 6 小时由 GitHub Actions 自动抓取 10 个数值模式、计算、发布，无需人工操作。
- 不依赖单一模型：把各模型订正到雪场的山脚 / 山腰 / 山顶后融合，同时给出各模型的范围和信心。
- 数据全部来自免费开放的来源（见[数据来源](#数据来源与署名)）。

当前是**第一阶段（MVP）**：10 个雪场、逐小时 7 天、逐日 16 天、多模型对比、本地收藏。后续阶段见[路线图](#路线图)。

## 架构

```
TokenFlyAI/snow（本仓库，公开）                       ccyjava/tokenfly（主站，私有）
┌──────────────────────────────────────────┐        ┌─────────────────────────────┐
│ data/resorts.yaml      雪场库            │        │ aiverse/snow/  静态外壳     │
│ pipeline/              Python 数据管道   │        │ snow_site.py   /snow 路由   │
│   ingest/   Open-Meteo 多模型抓取        │        └──────────────┬──────────────┘
│   process/  订正·雪线·雪水比·融合·聚合   │   scripts/deploy_shell.sh（仅代码变动时）
│   publish/  生成静态 JSON                │                       │
│ web/                   Next.js 静态导出  │───────────────────────┘
│ .github/workflows/                       │
│   forecast.yml  每 6 小时 ──────────────────▶ GitHub Pages
│   ci.yml        测试 + 前端构建          │     https://tokenflyai.github.io/snow/data/v1/
└──────────────────────────────────────────┘                       ▲
                                                                   │ fetch (CORS)
                              浏览器  https://tokenfly.ai/snow/ ───┘
```

为什么分成两处：tokenfly.ai 是 Render 上的 Python 服务，推送主站仓库会重启整个主站。预报数据每 6 小时变一次，所以**数据**走本仓库的 GitHub Pages（Actions 以 artifact 发布，不进 git 历史），主站仓库里只放**不含数据的页面外壳**，只有改了前端代码才需要重新部署。以后迁移到 Cloudflare R2 只需改 `NEXT_PUBLIC_DATA_BASE`。

### 发布的数据（`data/v1/`）

| 文件 | 内容 |
|---|---|
| `manifest.json` | 运行时间、各模型是否可用、API 用量、来源署名。最后写入，存在即表示本次运行完整 |
| `resorts.json` | 所有雪场的元数据 + 24h / 72h / 7 天 / 16 天降雪汇总（首页、列表、排行用） |
| `resort/{id}.json` | 逐小时 168h（三个海拔的气温、降雪、降水类型、雪线、0°C 层、山顶风）、逐日 16 天（夜间 / 白天降雪、范围、信心、雪质）、各模型逐日降雪 |

统一用公制（cm、mm、°C、m、km/h），单位换算在前端做。

## 计算方法

| 步骤 | 做法 | 代码 |
|---|---|---|
| 海拔订正 | 请求时 `elevation=nan` 取格点原始值和格点海拔；用模型自己的气压层温度求该层递减率（限制在 3–9.8°C/km，缺省 6.5），把 2m 气温订正到三个海拔 | `process/lapse.py` |
| 0°C 层、雪线 | 从气压层廓线自上而下找最高的 0°C 层；雪线取湿球温度 +0.5°C 的高度（NWS/NBM 的定义），没有湿度时退化为 0°C 层 − 300m | `process/snowlevel.py` |
| 降水类型 | 雪线以上全是雪，往下 300m 线性过渡到雨；每个海拔分别判断，所以同一场降水可能山顶下雪、山脚下雨 | `process/snowlevel.py` |
| 雪水比 | Kuchera 法（气柱最高温度），上限 25:1；风大时最多再降 35%（风压实） | `process/slr.py` |
| 没有气压层的模型 | 例如 NBM：降水量和 2m 气温用它自己的，雪线和递减率借用其他模型的中位数 | `process/derive.py` |
| 融合 | 按预报时效的经验权重：0–48h 高分辨率模型（HRRR、RRFS、HRDPS、NBM）权重大，3–10 天以 ECMWF / NBM / GFS 为主；缺数据的模型自动剔除并重新归一 | `process/blend.py`、`config.py` |
| 范围与信心 | 各模型日降雪量的加权 10% / 90% 分位；信心来自模型分歧，并随时效封顶（6 天以上最高"中"，10 天以上一律"低"） | `process/blend.py` |
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
python -m pytest -q                              # 68 个单元测试 + 回测
python -m pipeline.run --out site/data/v1        # 抓取并生成 JSON（约 10 秒，约 270 次加权 API 调用）
python -m pipeline.run --resorts alta,vail       # 只跑部分雪场

# 前端（Node 20+）
cd web && npm install
NEXT_PUBLIC_DATA_BASE=/snow/data/v1 npm run build   # 本地数据；不设则读线上 GitHub Pages
```

要在本机看完整效果，把 `web/out/` 复制到主站仓库的 `aiverse/snow/`（本地数据再复制 `site/data` 到 `aiverse/snow/data`），启动主站 `PORT=10081 python server.py`，打开 `http://localhost:10081/snow/`。

## 如何加雪场

1. 在 `data/resorts.yaml` 的 `resorts:` 下加一条（字段说明在文件头部）。坐标取主雪道区域中心（OSM `landuse=winter_sports` 的中心点），不要用山脚小镇；海拔和坐标各写明来源，拿不准的标 `needs_review: true`。
2. 新区域要在 `regions:` 里加一行。
3. `python -m pytest -q`（会校验整个雪场库），然后提交推送：数据在下一次定时运行时自动包含新雪场。
4. 运行 `scripts/deploy_shell.sh` 并推送主站仓库，新雪场的页面才会出现（外壳里有每个雪场的静态路由）。

新国家需要区域模型时，在 `pipeline/config.py` 的 `MODELS` 里加一条 `ModelSpec` 并在 `BLEND_WEIGHTS` 里给权重。

## 部署

| 什么 | 怎么更新 |
|---|---|
| 预报数据 | 全自动：`.github/workflows/forecast.yml` 每天 02:37 / 08:37 / 14:37 / 20:37 UTC 运行，也可在 Actions 页手动触发。失败时不发布（线上保留上一版）并自动开一个 issue |
| 页面外壳 | `scripts/deploy_shell.sh` 构建并复制到 `../tokenfly/aiverse/snow/`，然后在主站仓库里提交推送，Render 自动部署 |
| 主站路由 | 主站仓库的 `snow_site.py`（`register_snow(app)`）：`/snow` → 302 `/snow/`，目录自动找 `index.html`，带路径穿越校验 |

PWA 的 manifest 和 service worker 的 scope 都是 `/snow/`：页面走网络优先（离线时用缓存），带哈希的静态资源走缓存优先，预报 JSON 走 stale-while-revalidate。

## 数据来源与署名

- [Open-Meteo](https://open-meteo.com/)（CC BY 4.0）：ECMWF IFS / AIFS、NOAA GFS / NBM / HRRR / RRFS、DWD ICON、加拿大 GEM / HRDPS、JMA。免费档仅限非商用：600 次/分钟、5,000 次/小时、10,000 次/天；超过 10 个变量或 14 天按比例多计。
- 回测观测：[USDA NRCS SNOTEL](https://www.nrcs.usda.gov/wps/portal/wcc/home/)（公有领域）。
- 雪场坐标：© OpenStreetMap 贡献者（ODbL）；海拔：维基百科与雪场官网。

页面的「数据与方法」页会显示每次运行的模型状态和来源。

## 已知限制

- 各海拔的降水量相同，没有做地形增幅；模型格点降水本身在陡峭地形上会偏少或偏多。
- 雪水比的风修正、融合权重都是经验值，第 4 阶段的验证系统会按雪场用实测替换。
- 信心目前只看确定性模型之间的分歧，还没有接入集合预报。
- 10 天以后的逐日数值只有趋势参考价值，页面上做了淡化显示。
- Whistler Blackcomb（山顶海拔两个来源不一致）和 Niseko Grand Hirafu（坐标为估计）标了 `needs_review`。
- Open-Meteo 文档显示 HRRR、ICON Global 等标有停用日期（未能二次确认）；模型缺数据时会被自动剔除并在页面标注。

## 路线图

1. ✅ MVP：10 个雪场、多模型抓取、订正 + 雪线 + 雪水比、详情页、收藏、自动更新
2. 集合预报（ECMWF ENS、GEFS、GEM）+ 概率与信心；地图和排行榜；周尺度展望；Ikon / Epic 全部雪场。注意额度：全量每点约 30 次加权调用，约 280 个点做不到每 6 小时全量，需要分档（重点雪场每 6 小时、其余每天一次精简模型集）
3. Claude 每日雪报（中 / 英，结构化 JSON + 数值校验，读 NWS AFD）
4. SNOTEL / 雪场雪报验证 + 自适应权重 + 准确率页面
5. 登录与跨设备同步（Supabase）、邮件粉雪警报、月 / 季展望、数据迁移到 Cloudflare R2
