export type Level = "base" | "mid" | "summit";
export const LEVELS: Level[] = ["base", "mid", "summit"];
export type ByLevel<T = number | null> = Record<Level, T>;
export type PassTier = "unlimited" | "7day" | "5day" | "2day";
export type Confidence = "high" | "medium" | "low";
export type Quality = "powder" | "packed" | "heavy" | "none";

export interface Region { id: string; name: string; name_zh: string }

export interface ResortMeta {
  id: string; name: string; name_zh: string | null; destination: string | null;
  passes: Partial<Record<"ikon" | "epic", PassTier>>;
  country: string; state: string | null; region: string;
  lat: number; lon: number; elevation_m: ByLevel<number>; timezone: string;
  needs_review: boolean;
}

export interface Summary {
  snow_24h_cm: ByLevel; snow_72h_cm: ByLevel; snow_7d_cm: ByLevel; snow_16d_cm: ByLevel;
  next_snow: { date: string; snow_cm: ByLevel } | null;
  daily_mid_cm: (number | null)[];
}

export interface IndexResort extends ResortMeta { summary: Summary; dates: string[]; n_models: number }
export interface ResortIndex { schema_version: number; generated_at: string; regions: Region[]; resorts: IndexResort[] }

export interface ModelInfo {
  id: string; label: string; kind: string; status: "ok" | "missing";
  grid_elevation_m?: number | null; horizon_h?: number; has_profile?: boolean;
}

export interface Daily {
  date: string; lead_days: number;
  snow_night_cm: ByLevel; snow_day_cm: ByLevel; snow_cm: ByLevel; snow_low_cm: ByLevel; snow_high_cm: ByLevel;
  n_models: number; confidence: Confidence;
  precip_mm: number | null; rain_base_mm: number | null;
  temp_max_c: { base: number | null; summit: number | null };
  temp_min_c: { base: number | null; summit: number | null };
  snow_level_m: { min: number | null; max: number | null; during_precip: boolean };
  freezing_level_m: number | null; gust_max_kmh: number | null; wind_avg_kmh: number | null;
  cloud_pct: number | null; slr: number | null; quality: Quality;
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
  summary: Summary; hourly: Hourly; daily: Daily[];
  by_model_daily_cm: Record<string, ByLevel<(number | null)[]>>;
}

export interface Manifest {
  schema_version: number; generated_at: string; resort_count: number;
  models: { id: string; label: string; kind: string; status: string; resorts_ok: number; resorts_requested: number; error?: string }[];
  sources: { name: string; url: string; license: string }[]; attribution: string;
}
