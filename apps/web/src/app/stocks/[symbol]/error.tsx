"use client";

import { RouteErrorState } from "@/components/market/route-error-state";

export default function StockDetailErrorPage({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteErrorState
      title="The stock detail view could not be loaded"
      description="The backend request for detail, news, or analysis data did not complete successfully. Try the request again or return to the dashboard."
      reset={reset}
    />
  );
}

