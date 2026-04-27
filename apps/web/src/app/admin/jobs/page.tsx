import { AdminJobsView } from "@/components/admin/admin-jobs-view";
import { getAdminJobsStatus } from "@/lib/api";
import type { AdminJobStatusResponse } from "@/lib/types";

const EMPTY_STATUS: AdminJobStatusResponse = {
  generated_at: new Date(0).toISOString(),
  jobs: [],
};

export default async function AdminJobsPage() {
  const status = await getAdminJobsStatus().catch(() => EMPTY_STATUS);

  return <AdminJobsView status={status} />;
}
