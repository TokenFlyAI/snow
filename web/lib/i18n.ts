export type Lang = "zh" | "en";

const dict = {
  appName: { zh: "雪报", en: "Snow" },
  tagline: { zh: "多模型融合的滑雪场降雪预报", en: "Multi-model snow forecasts for ski resorts" },
  myResorts: { zh: "我的雪场", en: "My resorts" },
  allResorts: { zh: "全部雪场", en: "All resorts" },
  about: { zh: "方法", en: "Method" },
  map: { zh: "地图", en: "Map" },
  rank: { zh: "排行", en: "Ranking" },
  navRank: { zh: "排行", en: "Rank" },
  navResorts: { zh: "全部雪场", en: "Resorts" },
  navAbout: { zh: "方法", en: "About" },
  follow: { zh: "关注", en: "Follow" },
  following: { zh: "已关注", en: "Following" },
  unfollow: { zh: "取消关注", en: "Unfollow" },
  search: { zh: "搜索雪场", en: "Search resorts" },
  all: { zh: "全部", en: "All" },
  noFavorites: { zh: "还没有关注雪场", en: "No resorts followed yet" },
  noFavoritesHint: { zh: "关注后，这里会汇总每个雪场未来 24 小时到 16 天的降雪。", en: "Follow resorts to see their next 24 hours to 16 days of snow here." },
  pickResorts: { zh: "选择雪场", en: "Pick resorts" },
  leaderboard: { zh: "未来 7 天降雪排行", en: "Most snow, next 7 days" },
  rankTitle: { zh: "降雪排行", en: "Snowfall ranking" },
  rankHint: { zh: "按滑雪日累计（今天的滑雪日从昨天 16:00 算起）。细线是集合预报的 10%–90% 范围；16 天的后 6 天用集合平均值。", en: "Ski-day totals (today's ski day began at 4 pm yesterday). The thin line is the ensemble 10–90 % range; the last 6 of the 16 days use the ensemble mean." },
  seeAll: { zh: "查看完整排行", en: "Full ranking" },
  showAll: { zh: "显示全部", en: "Show all" },
  d3: { zh: "3 天", en: "3 days" },
  d7: { zh: "7 天", en: "7 days" },
  d16: { zh: "16 天", en: "16 days" },
  allRegions: { zh: "全部地区", en: "All regions" },
  region: { zh: "地区", en: "Region" },
  regionGroups: { zh: "大区", en: "Areas" },
  regionsSingle: { zh: "地区", en: "Regions" },
  mapTitle: { zh: "区域总览", en: "Region overview" },
  mapHint: { zh: "圆点颜色 = 所选天数内的累计降雪。点一个雪场看详情。", en: "Dot colour = total snowfall over the selected days. Tap a resort for details." },
  mapLegend: { zh: "累计降雪", en: "Snowfall" },
  mapLoading: { zh: "地图加载中…", en: "Loading map…" },
  mapError: { zh: "地图底图加载失败，下面的列表仍可使用。", en: "The base map failed to load; the list below still works." },
  resortsCount: { zh: "个雪场", en: "resorts" },
  details: { zh: "详情", en: "Details" },
  cumTitle: { zh: "累计降雪", en: "Accumulated snowfall" },
  cumHint: { zh: "从今天起累计会下多少。线是我们的预报；深色带是集合预报成员的 10%–90% 范围，浅色带是最少到最多。越往后越不确定，所以带越来越宽。", en: "Total from today on. The line is our forecast; the darker band is the 10–90 % range of the ensemble members, the lighter band their minimum to maximum. The further out, the less certain, so the fan opens." },
  cumForecast: { zh: "预报", en: "Forecast" },
  cumBand: { zh: "10%–90%", en: "10–90 %" },
  cumMinMax: { zh: "最少–最多", en: "Min–max" },
  cumMin: { zh: "最少", en: "Min" },
  cumMax: { zh: "最多", en: "Max" },
  showTable: { zh: "表格", en: "Table" },
  ensBand: { zh: "集合 10%–90%", en: "Ensemble 10–90 %" },
  ensMedian: { zh: "集合中位数", en: "Ensemble median" },
  probTitle: { zh: "第 11–16 天：只给概率", en: "Days 11–16: probabilities only" },
  probHint: { zh: "这么远的单日数值没有意义，所以只给集合成员中达到某个量的比例。", en: "Single-day amounts this far out mean little, so this is the share of ensemble members reaching each amount." },
  probAtLeast: { zh: "概率", en: "chance" },
  median: { zh: "中位数", en: "Median" },
  members: { zh: "成员", en: "members" },
  agreement: { zh: "成员一致度", en: "Member agreement" },
  outlook: { zh: "第 3–5 周展望", en: "Weeks 3–5 outlook" },
  outlookHint: { zh: "35 天集合预报的周累计降雪（山腰）。只能当趋势看：数字是成员中达到该累计量的比例，不是确定的预报。", en: "Weekly snowfall at mid-mountain from the 35-day ensembles. Trend only: each number is the share of members reaching that weekly total, not a forecast of what will happen." },
  week: { zh: "第 {n} 周", en: "Week {n}" },
  weekTotal: { zh: "周累计", en: "weekly total" },
  ensembleInfo: { zh: "集合预报", en: "Ensembles" },
  calibration: { zh: "订正系数", en: "calibration factor" },
  tierFeatured: { zh: "重点雪场 · 每 6 小时更新 · 全部模型", en: "Featured · every 6 hours · all models" },
  tierStandard: { zh: "每天更新一次 · 3 个模型 + GEFS 集合", en: "Updated once a day · 3 models + GEFS ensemble" },
  rangeFromModels: { zh: "模型间范围", en: "model spread" },
  ensembleStatus: { zh: "本次运行的集合预报", en: "Ensembles in this run" },
  budget: { zh: "API 额度", en: "API budget" },
  thisRun: { zh: "本次运行", en: "This run" },
  perDay: { zh: "每天合计（按计划 4 次运行估算）", en: "Per day (4 scheduled runs, estimated)" },
  days3: { zh: "3 天", en: "3 days" },
  next24h: { zh: "24 小时", en: "24 h" },
  next72h: { zh: "72 小时", en: "72 h" },
  next7d: { zh: "7 天", en: "7 days" },
  next16d: { zh: "16 天", en: "16 days" },
  nextSnow: { zh: "下一场雪", en: "Next snow" },
  noSnowAhead: { zh: "10 天内没有明显降雪", en: "No significant snow in 10 days" },
  today: { zh: "今天", en: "Today" },
  base: { zh: "山脚", en: "Base" },
  mid: { zh: "山腰", en: "Mid" },
  summit: { zh: "山顶", en: "Summit" },
  elevation: { zh: "海拔", en: "Elevation" },
  daily: { zh: "逐日预报", en: "Daily forecast" },
  dailyHint: { zh: "夜间 = 前一天 16:00 到当天 08:00（早上起来有多少新雪）；白天 = 08:00 到 16:00。灰色带是集合预报成员的 10%–90% 范围，虚线是中位数。第 11 天起不再给单一数值。", en: "Night = 4 pm the day before to 8 am (what you wake up to); day = 8 am to 4 pm. The grey band is the 10–90 % range of the ensemble members, the dashed line their median. From day 11 there is no single value." },
  night: { zh: "夜间", en: "Overnight" },
  day: { zh: "白天", en: "Daytime" },
  total: { zh: "合计", en: "Total" },
  range: { zh: "范围", en: "Range" },
  date: { zh: "日期", en: "Date" },
  temp: { zh: "气温", en: "Temp" },
  tempHiLo: { zh: "最高 / 最低", en: "High / low" },
  snowLevel: { zh: "雪线", en: "Snow level" },
  freezingLevel: { zh: "0°C 层", en: "Freezing level" },
  wind: { zh: "风", en: "Wind" },
  gust: { zh: "阵风", en: "Gust" },
  summitGust: { zh: "山顶阵风", en: "Summit gust" },
  rainBase: { zh: "山脚降雨", en: "Rain at base" },
  quality: { zh: "雪质", en: "Snow type" },
  confidence: { zh: "信心", en: "Confidence" },
  high: { zh: "高", en: "High" },
  medium: { zh: "中", en: "Medium" },
  low: { zh: "低", en: "Low" },
  powder: { zh: "干粉", en: "Powder" },
  packed: { zh: "普通", en: "Average" },
  heavy: { zh: "湿重", en: "Heavy" },
  models: { zh: "多模型对比", en: "Model comparison" },
  modelsHint: { zh: "每个确定性模型各自的日降雪量（前 10 天）。柱子越分散，预报越不确定。", en: "Each deterministic model's own daily snowfall (first 10 days). The more the bars disagree, the less certain the forecast." },
  blend: { zh: "融合", en: "Blend" },
  modelMissing: { zh: "本次缺数据，已从融合中剔除", en: "no data this run, left out of the blend" },
  gridElevation: { zh: "格点海拔", en: "grid elevation" },
  horizon: { zh: "时效", en: "horizon" },
  hourly: { zh: "逐小时（7 天）", en: "Hourly (7 days)" },
  hourlySnow: { zh: "每小时降雪", en: "Hourly snowfall" },
  hourlyTemp: { zh: "气温：山脚与山顶", en: "Temperature: base and summit" },
  hourlySnowLevel: { zh: "雪线与雪场海拔", en: "Snow level vs resort elevations" },
  hourlyWind: { zh: "山顶风速与阵风", en: "Summit wind and gusts" },
  feelsLike: { zh: "体感", en: "Feels like" },
  precip: { zh: "降水", en: "Precip" },
  ptype: { zh: "降水类型", en: "Precip type" },
  snow: { zh: "雪", en: "Snow" },
  mix: { zh: "雨夹雪", en: "Mix" },
  rain: { zh: "雨", en: "Rain" },
  cloud: { zh: "云量", en: "Cloud" },
  updated: { zh: "更新于", en: "Updated" },
  loading: { zh: "加载中…", en: "Loading…" },
  loadError: { zh: "数据加载失败，显示的可能是上次缓存。", en: "Could not load data; you may be seeing the last cached copy." },
  needsReview: { zh: "坐标或海拔待核对", en: "Coordinates or elevations need review" },
  units: { zh: "单位", en: "Units" },
  theme: { zh: "主题", en: "Theme" },
  table: { zh: "表格", en: "Table" },
  chart: { zh: "图表", en: "Chart" },
  sources: { zh: "数据来源", en: "Data sources" },
  method: { zh: "计算方法", en: "How it is computed" },
  modelStatus: { zh: "本次运行的模型", en: "Models in this run" },
  unlimited: { zh: "不限", en: "Unlimited" },
  days7: { zh: "7 天", en: "7 days" },
  days5: { zh: "5 天", en: "5 days" },
  days2: { zh: "2 天", en: "2 days" },
  back: { zh: "返回", en: "Back" },
  farOut: { zh: "第 11 天起只给概率", en: "Probabilities only from day 11" },
  mountain: { zh: "参考海拔", en: "Elevation shown" },
} as const;

export type Key = keyof typeof dict;
export const t = (k: Key, lang: Lang): string => dict[k][lang];

const WEEK = { zh: ["周日", "周一", "周二", "周三", "周四", "周五", "周六"], en: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] };

/** "2026-11-13" -> "周五 11/13" */
export function fmtDate(iso: string, lang: Lang, short = false): string {
  const [y, m, d] = iso.split("-").map(Number);
  const wd = WEEK[lang][new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
  return short ? `${wd}` : `${wd} ${m}/${d}`;
}

export function fmtUpdated(iso: string, lang: Lang): string {
  const d = new Date(iso);
  return d.toLocaleString(lang === "zh" ? "zh-CN" : "en-US", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export const tierKey = (tier: string): Key =>
  tier === "unlimited" ? "unlimited" : tier === "7day" ? "days7" : tier === "5day" ? "days5" : tier === "3day" ? "days3" : "days2";

/** "2026-11-25", "2026-12-01" -> "11/25–12/1" */
export function fmtRange(a: string, b: string): string {
  const md = (iso: string) => { const [, m, d] = iso.split("-").map(Number); return `${m}/${d}`; };
  return `${md(a)}–${md(b)}`;
}

/** 0.42 -> "42%"; tiny non-zero shares are shown as "<5%" rather than 0. */
export function fmtProb(p: number | null | undefined): string {
  if (p === null || p === undefined || !Number.isFinite(p)) return "–";
  if (p > 0 && p < 0.05) return "<5%";
  if (p < 1 && p > 0.95) return ">95%";
  return `${Math.round(p * 100)}%`;
}
