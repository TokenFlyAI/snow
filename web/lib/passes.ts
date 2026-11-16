import generated from "./resorts.generated.json";
import type { ResortMeta } from "./types";

/**
 * Pass filters: the top tier from data/resorts.yaml (Ikon Pass, Epic Pass) and the lower-tier
 * products from data/pass_products.yaml (Ikon Base, Epic Local) with their blackout dates.
 */
export type Product = "ikon-base" | "epic-local";
export type PassFilter = "all" | "ikon" | "epic" | Product;
export interface ProductAccess { days: "unlimited" | number; shared: boolean; blackout: [string, string][]; consecutive: boolean }

const G = generated as unknown as {
  products: { id: Product; pass: "ikon" | "epic"; name: string }[];
  product_access: Record<Product, Record<string, ProductAccess>>;
};
export const PRODUCTS = G.products;
export const PASS_FILTERS: PassFilter[] = ["all", "ikon", ...PRODUCTS.filter((p) => p.pass === "ikon").map((p) => p.id),
  "epic", ...PRODUCTS.filter((p) => p.pass === "epic").map((p) => p.id)];

export const isProduct = (f: string): f is Product => PRODUCTS.some((p) => p.id === f);
export const productAccess = (p: Product, rid: string): ProductAccess | undefined => G.product_access[p]?.[rid];
export const passName = (f: Exclude<PassFilter, "all">) => (f === "ikon" ? "Ikon" : f === "epic" ? "Epic" : PRODUCTS.find((p) => p.id === f)!.name);

/** Is this date a blackout date of the product at this resort? */
export const blocked = (a: ProductAccess, iso: string) => a.blackout.some(([x, y]) => x <= iso && iso <= y);

/** Can a holder of `f` ski resort `rid` (on `date`, if given)? */
export function onPass(f: PassFilter, rid: string, passes: ResortMeta["passes"], date?: string): boolean {
  if (f === "all") return true;
  if (isProduct(f)) {
    const a = productAccess(f, rid);
    return !!a && !(date && blocked(a, date));
  }
  return !!passes[f];
}

/** The products a resort is on, for the resort page. */
export const productsOf = (rid: string) =>
  PRODUCTS.map((p) => ({ ...p, access: productAccess(p.id, rid) })).filter((p) => p.access);
