import { RESORTS } from "@/lib/resorts";
import ResortClient from "./ResortClient";

export function generateStaticParams() {
  return RESORTS.map((r) => ({ id: r.id }));
}
export const dynamicParams = false;

export default function Page({ params }: { params: { id: string } }) {
  return <ResortClient id={params.id} />;
}
