export type Lang = "zh" | "en";

const dict = {
  appName: { zh: "雪报", en: "Snow" },
  tagline: { zh: "多模型融合的滑雪场降雪预报", en: "Multi-model snow forecasts for ski resorts" },
  myResorts: { zh: "我的雪场", en: "My resorts" },
  allResorts: { zh: "全部雪场", en: "All resorts" },
  about: { zh: "数据与方法", en: "Data & method" },
  follow: { zh: "关注", en: "Follow" },
  following: { zh: "已关注", en: "Following" },
  unfollow: { zh: "取消关注", en: "Unfollow" },
  search: { zh: "搜索雪场", en: "Search resorts" },
  all: { zh: "全部", en: "All" },
  noFavorites: { zh: "还没有关注雪场", en: "No resorts followed yet" },
  noFavoritesHint: { zh: "关注后，这里会汇总每个雪场未来 24 小时到 16 天的降雪。", en: "Follow resorts to see their next 24 hours to 16 days of snow here." },
  pickResorts: { zh: "选择雪场", en: "Pick resorts" },
  leaderboard: { zh: "未来 7 天降雪排行", en: "Most snow, next 7 days" },
  next24h: { zh: "24 小时", en: "24 h" },
  next72h: { zh: "72 小时", en: "72 h" },
  next7d: { zh: "7 天", en: "7 days" },
  next16d: { zh: "16 天", en: "16 days" },
  nextSnow: { zh: "下一场雪", en: "Next snow" },
  noSnowAhead: { zh: "16 天内没有明显降雪", en: "No significant snow in 16 days" },
  today: { zh: "今天", en: "Today" },
  base: { zh: "山脚", en: "Base" },
  mid: { zh: "山腰", en: "Mid" },
  summit: { zh: "山顶", en: "Summit" },
  elevation: { zh: "海拔", en: "Elevation" },
  daily: { zh: "逐日预报", en: "Daily forecast" },
  dailyHint: { zh: "夜间 = 前一天 16:00 到当天 08:00（早上起来有多少新雪）；白天 = 08:00 到 16:00。细线为各模型的 10%–90% 范围。", en: "Night = 4 pm the day before to 8 am (what you wake up to); day = 8 am to 4 pm. Thin line: 10–90 % range across models." },
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
  modelsHint: { zh: "每个模型各自的日降雪量。柱子越分散，预报越不确定。", en: "Each model's own daily snowfall. The more the bars disagree, the less certain the forecast." },
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
  farOut: { zh: "10 天以后只有趋势参考价值", en: "Beyond 10 days: trend only" },
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
  tier === "unlimited" ? "unlimited" : tier === "7day" ? "days7" : tier === "5day" ? "days5" : "days2";
