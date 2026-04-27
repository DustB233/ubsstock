import { DataState } from "@/components/market/primitives";

export default function StockNotFoundPage() {
  return (
    <DataState
      eyebrow="Stock Detail"
      title="This stock is not in the tracked universe"
      description="The requested symbol or slug does not match one of the 15 seeded outbound-related stocks."
      action={{ href: "/", label: "Return to dashboard" }}
    />
  );
}
