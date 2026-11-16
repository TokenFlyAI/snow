"use client";
import { useEffect, useState } from "react";
import { useUser } from "@/components/Providers";
import { CLOSURES, cityById, cityName, driveTarget, fmtDrive, savedCity, useDrive } from "@/lib/drive";

/** "From Denver: ~2 h drive · Directions", for the home city picked on the Plan page. */
export function DriveLine({ id, lat, lon }: { id: string; lat: number; lon: number }) {
  const { t, lang } = useUser();
  const [from, setFrom] = useState("");
  useEffect(() => setFrom(savedCity()), []);
  const drive = useDrive(from);
  const city = cityById(from);
  const min = drive?.minutes[from]?.[id];
  if (!city || min == null) return null;
  const via = drive?.via[from]?.[id];
  const [dlat, dlon] = driveTarget(id, lat, lon);
  const maps = `https://www.google.com/maps/dir/?api=1&origin=${city.lat},${city.lon}&destination=${dlat},${dlon}&travelmode=driving`;
  return (
    <p className="mt-1 text-xs text-ink-2">
      {t("driveFrom").replace("{c}", cityName(city, lang))} <span className="num">{t("planDrive").replace("{t}", fmtDrive(min, lang))}</span>
      {via && <span className="text-ink-3" title={t("planDetourHint").replace("{p}", via.map((c) => CLOSURES[c] ?? c).join(", "))}> · {t("planDetour")}</span>}
      {" · "}<a className="underline decoration-line underline-offset-4" href={maps} target="_blank" rel="noopener noreferrer">{t("driveDirections")}</a>
    </p>
  );
}
