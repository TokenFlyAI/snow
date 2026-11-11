"use client";
import { LoadState, Updated } from "@/components/Bits";
import { useUser } from "@/components/Providers";
import { useManifest } from "@/lib/data";

const METHOD = {
  zh: [
    ["海拔订正", "模型地形是平滑的，格点海拔和雪场不一样。用模型自己的气压层温度求出实际递减率（限制在 3–9.8°C/km），把气温分别订正到山脚、山腰、山顶。"],
    ["雪线与降水类型", "雪线取湿球温度 +0.5°C 的高度（与美国国家气象局一致）。雪线以上是雪，往下 300 米逐渐变成雨，所以同一场降水可能山顶下雪、山脚下雨。"],
    ["雪水比", "不用固定 10:1。按 Kuchera 方法由气柱最高温度计算：接近 0°C 约 5–8:1（湿重），很冷时 15–20:1（干粉），大风时再打折。降雪量 = 液态降水 × 雪水比。"],
    ["多模型融合", "0–48 小时高分辨率模型权重大，3–10 天以 ECMWF、NBM、GFS 为主。某个模型缺数据时自动剔除。图上的细线是各模型的 10%–90% 范围。"],
    ["信心", "来自各模型之间的分歧，并随预报时效降低：6 天以上最高为中，10 天以上一律为低。"],
  ],
  en: [
    ["Elevation correction", "Model terrain is smoothed, so the grid cell is rarely at resort height. Temperatures are moved to base, mid and summit with the lapse rate the model itself has in that layer (kept within 3–9.8 °C/km)."],
    ["Snow level and precipitation type", "The snow level is where the wet-bulb temperature is +0.5 °C (the NWS convention). Above it is snow; over the 300 m below it turns to rain, so one storm can be snow up top and rain at the base."],
    ["Snow-to-liquid ratio", "No fixed 10:1. The Kuchera method uses the warmest temperature in the column: about 5–8:1 near freezing (heavy), 15–20:1 in cold air (powder), reduced in strong wind. Snowfall = liquid × ratio."],
    ["Blending", "High-resolution models lead in the first 48 hours; ECMWF, NBM and GFS lead from 3 to 10 days. A model with no data is left out. The thin line on the charts is the 10–90 % range across models."],
    ["Confidence", "From how much the models disagree, lowered with lead time: at most medium beyond 6 days, always low beyond 10."],
  ],
};

export default function About() {
  const { t, ready, lang } = useUser();
  const { data, loading, error } = useManifest();
  if (!ready) return null;
  return (
    <div>
      <section className="card p-4">
        <h2 className="text-base font-semibold">{t("method")}</h2>
        <dl className="mt-3 space-y-3">
          {METHOD[lang].map(([k, v]) => (
            <div key={k}><dt className="text-sm font-medium">{k}</dt><dd className="mt-0.5 text-sm leading-6 text-ink-2">{v}</dd></div>
          ))}
        </dl>
      </section>

      <LoadState loading={loading} error={error} />
      {data && (
        <>
          <section className="card mt-4 p-4">
            <div className="flex items-center justify-between"><h2 className="text-base font-semibold">{t("modelStatus")}</h2><Updated iso={data.generated_at} /></div>
            <ul className="mt-3 divide-y divide-line text-sm">
              {data.models.map((m) => (
                <li key={m.id} className="flex items-center justify-between py-2">
                  <span>{m.label} <span className="text-xs text-ink-3">{m.id}</span></span>
                  <span className="num text-ink-2">{m.status === "ok" ? `✓ ${m.resorts_ok}/${m.resorts_requested}` : `⚠ ${t("modelMissing")}`}</span>
                </li>
              ))}
            </ul>
          </section>
          <section className="card mt-4 p-4">
            <h2 className="text-base font-semibold">{t("sources")}</h2>
            <p className="mt-2 text-sm text-ink-2">{data.attribution}</p>
            <ul className="mt-3 space-y-1.5 text-sm">
              {data.sources.map((s) => (
                <li key={s.name}><a className="underline decoration-line underline-offset-4" href={s.url} target="_blank" rel="noreferrer">{s.name}</a> <span className="text-xs text-ink-3">· {s.license}</span></li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
