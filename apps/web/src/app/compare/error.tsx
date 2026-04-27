"use client";

import { RouteErrorState } from "@/components/market/route-error-state";

export default function CompareErrorPage({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteErrorState
      title="The comparison view could not be loaded"
      description="The comparison API request failed before the tables could render. Retry the request to refresh the selected symbols."
      reset={reset}
    />
  );
}

