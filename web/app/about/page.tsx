"use client";
import { LoadState, Updated } from "@/components/Bits";
import { useUser } from "@/components/Providers";
import { useManifest } from "@/lib/data";

const METHOD = {
  zh: [
    ["海拔订正", "模型地形是平滑的，格点海拔和雪场不一样。用模型自己的气压层温度求出实际递减率（限制在 3–9.8°C/km），把气温分别订正到山脚、山腰、山顶。"],
    ["雪线与降水类型", "雪线取湿球温度 +0.5°C 的高度（与美国国家气象局一致）。雪线以上是雪，往下 300 米逐渐变成雨，所以同一场降水可能山顶下雪、山脚下雨。"],
    ["雪水比", "不用固定 10:1。按 Kuchera 方法由气柱最高温度计算：接近 0°C 约 5–8:1（湿重），很冷时 15–20:1（干粉），大风时再打折。降雪量 = 液态降水 × 雪水比。"],
    ["多模型融合（第 1–10 天）", "0–48 小时高分辨率模型权重大，3–10 天以 ECMWF、NBM、GFS 为主。欧洲加入 Météo-France AROME、MeteoSwiss ICON 和 ICON-D2，其他地区加入英国气象局全球模型。某个模型缺数据时自动剔除。"],
    ["集合预报", "ECMWF ENS（51 个成员）、GEFS（31）、加拿大 GEPS（21）、ICON-EPS（40）。每个成员都是把初始状态稍作扰动后重跑一遍的预报，成员之间的差别就是不确定性。成员的降雪先按当天的雪水比换算，再乘一个订正系数，使未来 10 天的集合平均总量与多模型融合一致（全球集合分辨率低，山区降水系统性偏少）。"],
    ["范围与信心", "逐日图上的灰色带是集合成员的 10%–90% 范围。信心 = 落在预报值 ±50%（至少 ±5 cm）以内的成员比例：一半以上为高，四分之一以上为中，否则为低；7 天以上最高为中。"],
    ["第 11 天以后", "不再给单日数值，只给概率：例如「≥15 cm 的概率 30%」表示 30% 的成员在那一天达到 15 cm。第 3–5 周只给周累计降雪的概率，来自 35 天的 GEFS 和 GEPS，只能当趋势看。"],
    ["更新频率", "重点雪场每 6 小时用全部模型更新；其余雪场每天在当地清晨前更新一次，用 ECMWF、GFS 和一个区域模型，集合只用 GEFS。这是免费数据额度（每天 10,000 次）决定的。"],
  ],
  en: [
    ["Elevation correction", "Model terrain is smoothed, so the grid cell is rarely at resort height. Temperatures are moved to base, mid and summit with the lapse rate the model itself has in that layer (kept within 3–9.8 °C/km)."],
    ["Snow level and precipitation type", "The snow level is where the wet-bulb temperature is +0.5 °C (the NWS convention). Above it is snow; over the 300 m below it turns to rain, so one storm can be snow up top and rain at the base."],
    ["Snow-to-liquid ratio", "No fixed 10:1. The Kuchera method uses the warmest temperature in the column: about 5–8:1 near freezing (heavy), 15–20:1 in cold air (powder), reduced in strong wind. Snowfall = liquid × ratio."],
    ["Blending (days 1–10)", "High-resolution models lead in the first 48 hours; ECMWF, NBM and GFS lead from 3 to 10 days. Europe adds Météo-France AROME, MeteoSwiss ICON and ICON-D2; other regions add the UK Met Office global model. A model with no data is left out."],
    ["Ensembles", "ECMWF ENS (51 members), GEFS (31), Canadian GEPS (21), ICON-EPS (40). Each member is the forecast re-run from a slightly perturbed start, so the differences between members are the uncertainty. Member snowfall is converted with the day's snow ratio and multiplied by one factor that makes the ensemble-mean total of the next 10 days match the blend (global ensembles are coarse and systematically dry in the mountains)."],
    ["Range and confidence", "The grey band on the daily chart is the 10–90 % range of the members. Confidence is the share of members within ±50 % (at least ±5 cm) of the forecast value: high from one half, medium from one quarter, otherwise low; at most medium beyond 7 days."],
    ["Beyond day 10", "No single-day amounts, only probabilities: “30 % chance of ≥ 15 cm” means 30 % of the members reach 15 cm that day. Weeks 3–5 give the chance of a weekly total from the 35-day GEFS and GEPS runs; treat it as a trend."],
    ["Update frequency", "Featured resorts are refreshed every 6 hours with every model. All others once a day before the local morning with ECMWF, GFS and one regional model, and GEFS as the only ensemble. The free data quota (10,000 calls a day) sets this limit."],
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
          {data.ensembles && data.ensembles.length > 0 && (
            <section className="card mt-4 p-4">
              <h2 className="text-base font-semibold">{t("ensembleStatus")}</h2>
              <ul className="mt-3 divide-y divide-line text-sm">
                {data.ensembles.map((m) => (
                  <li key={m.id} className="flex items-center justify-between py-2">
                    <span>{m.label} <span className="text-xs text-ink-3">{m.members} {t("members")} · {m.days}d</span></span>
                    <span className="num text-ink-2">{m.status === "ok" ? `✓ ${m.resorts_ok}/${m.resorts_requested}` : `⚠ ${t("modelMissing")}`}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {data.api_usage?.daily_estimate && (
            <section className="card mt-4 p-4">
              <h2 className="text-base font-semibold">{t("budget")}</h2>
              <dl className="num mt-3 space-y-1.5 text-sm">
                <div className="flex justify-between gap-3"><dt className="text-ink-2">{t("thisRun")}{data.run ? ` (${data.run.refreshed_deterministic}/${data.run.resorts})` : ""}</dt><dd>{Math.round(data.api_usage.weighted_calls).toLocaleString("en-US")}</dd></div>
                <div className="flex justify-between gap-3"><dt className="text-ink-2">{t("perDay")}</dt><dd><b>{Math.round(data.api_usage.daily_estimate.total).toLocaleString("en-US")}</b> / {(data.api_usage.daily_limit ?? 10000).toLocaleString("en-US")}</dd></div>
              </dl>
              <div className="mt-2 h-1.5 rounded-full bg-surface-2" aria-hidden>
                <div className="h-1.5 rounded-full" style={{ width: `${Math.min(100, (data.api_usage.daily_estimate.total / (data.api_usage.daily_limit ?? 10000)) * 100)}%`, background: "var(--series-1)" }} />
              </div>
            </section>
          )}
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
