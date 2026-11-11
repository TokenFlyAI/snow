import Link from "next/link";

export default function NotFound() {
  return (
    <div className="py-16 text-center">
      <p className="text-lg font-semibold">404</p>
      <Link href="/" className="mt-3 inline-block text-sm underline">雪报 · Snow</Link>
    </div>
  );
}
