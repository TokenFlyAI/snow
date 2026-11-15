export type Level = "base" | "mid" | "summit";
export const LEVELS: Level[] = ["base", "mid", "summit"];
export type ByLevel<T = number | null> = Record<Level, T>;
export type PassTier = "unlimited" | "7day" | "5day" | "3day" | "2day";
export type Tier = "featured" | "standard";
export type Confidence = "high" | "medium" | "low";
export type Quality = "powder" | "packed" | "heavy" | "none";

export interface Region { id: string; name: string; name_zh: string }

export interface ResortMeta {
  id: string; name: string; name_zh: string | null; destination: string | null;
  passes: Partial<Record<"ikon" | "epic", PassTier>>;
  country: string; state: string | null; region: string;
  lat: number; lon: number; elevation_m: ByLevel<number>; timezone: string;
  needs_review: boolean; tier?: Tier;
}

/** Ski-day total (today's ski day started at 16:00 yesterday) with the ensemble 10-90 % range. */
export interface WindowTotal { cm: ByLevel; low_cm: ByLevel | null; high_cm: ByLevel | null; days: number; complete: boolean }
export type WindowKey = "3d" | "7d" | "16d";

export interface Summary {
  snow_24h_cm: ByLevel; snow_72h_cm: ByLevel; snow_7d_cm: ByLevel; snow_16d_cm: ByLevel;
  totals: Record<WindowKey, WindowTotal>;
  next_snow: { date: string; snow_cm: ByLevel } | null;
  daily_mid_cm: (number | null)[];
}

export interface IndexResort extends ResortMeta {
  tier: Tier; generated_at: string; ensemble_at: string | null;
  summary: Summary; dates: string[]; n_models: number; n_members: number;
  outlook: { week: number; p50_cm: number | null; prob: Record<string, number | null> }[];
}
export interface ResortIndex { schema_version: number; generated_at: string; regions: Region[]; resorts: IndexResort[] }

export interface ModelInfo {
  id: string; label: string; kind: string; status: "ok" | "missing";
  grid_elevation_m?: number | null; horizon_h?: number; has_profile?: boolean;
}

/** Ensemble distribution of one ski day (cm). prob: chance of at least 2.5 / 15 cm, 0..1. */
export interface EnsDay {
  p10: ByLevel; p50: ByLevel; p90: ByLevel; mean: ByLevel;
  prob: Record<string, ByLevel>; n_members: number;
  /** share of members close to the point value (point days only) */
  agreement?: number | null;
}

/** Ski days D+0..D+9: point values from the blend. */
export interface Daily {
  date: string; lead_days: number; kind: "point";
  snow_night_cm: ByLevel; snow_day_cm: ByLevel; snow_cm: ByLevel; snow_low_cm: ByLevel; snow_high_cm: ByLevel;
  range_source: "ensemble" | "models"; ens: EnsDay | null;
  n_models: number; confidence: Confidence;
  precip_mm: number | null; rain_base_mm: number | null;
  temp_max_c: { base: number | null; summit: number | null };
  temp_min_c: { base: number | null; summit: number | null };
  snow_level_m: { min: number | null; max: number | null; during_precip: boolean };
  freezing_level_m: number | null; gust_max_kmh: number | null; wind_avg_kmh: number | null;
  cloud_pct: number | null; slr: number | null; quality: Quality;
}

/** Ski days D+10..D+15: probabilities only. */
export interface ProbDay { date: string; lead_days: number; kind: "prob"; ens: EnsDay }
export type DayEntry = Daily | ProbDay;

/** Weeks 3-5: weekly total at mid-mountain, as probabilities. */
export interface OutlookWeek {
  week: number; start: string; end: string;
  p10_cm: number | null; p50_cm: number | null; p90_cm: number | null; mean_cm: number | null;
  prob: Record<string, number | null>; n_members: number; models: string[];
}

export interface EnsembleInfo {
  generated_at: string | null; level: Level; elevation_m: number;
  models: { id: string; label: string; members: number; horizon_days: number }[];
  calibration: { factor: number; slr_default: number; days: number; blend_cm: number; ensemble_cm: number };
}

export interface Hourly {
  time: string[];
  temp_c: ByLevel<(number | null)[]>; feels_summit_c: (number | null)[];
  precip_mm: (number | null)[]; snow_cm: ByLevel<(number | null)[]>; ptype: ByLevel<number[]>;
  snow_level_m: (number | null)[]; freezing_level_m: (number | null)[]; slr: (number | null)[];
  wind_summit_kmh: (number | null)[]; gust_summit_kmh: (number | null)[];
  cloud_pct: (number | null)[]; visibility_m: (number | null)[];
}

export interface ResortDoc {
  schema_version: number; generated_at: string; resort: ResortMeta; models: ModelInfo[];
  ensemble: EnsembleInfo | null; outlook: OutlookWeek[];
  summary: Summary; hourly: Hourly;
  /** point days (D+0..D+9); older documents also carried the probability days here */
  daily: DayEntry[];
  /** probability-only days (D+10..D+15) */
  daily_prob?: ProbDay[];
  by_model_daily_cm: Record<string, ByLevel<(number | null)[]>>;
}

export interface Manifest {
  schema_version: number; generated_at: string; resort_count: number;
  models: { id: string; label: string; kind: string; status: string; resorts_ok: number; resorts_requested: number; error?: string }[];
  ensembles?: { id: string; label: string; members: number; days: number; status: string; resorts_ok: number; resorts_requested: number; error?: string }[];
  run?: { mode: string; slot_utc: number; resorts: number; featured: number; refreshed_deterministic: number; refreshed_ensemble: number; carried_over: number; failed: string[] };
  api_usage?: { requests: number; weighted_calls: number; by_kind?: Record<string, number>;
    daily_estimate?: { featured_deterministic: number; standard_deterministic: number; ensembles: number; total: number };
    daily_limit?: number; daily_target?: number };
  sources: { name: string; url: string; license: string }[]; attribution: string;
}
