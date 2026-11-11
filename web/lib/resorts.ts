import generated from "./resorts.generated.json";
import type { Region, ResortMeta } from "./types";

export const REGIONS = generated.regions as Region[];
export const RESORTS = generated.resorts as unknown as ResortMeta[];
export const resortById = (id: string) => RESORTS.find((r) => r.id === id);
