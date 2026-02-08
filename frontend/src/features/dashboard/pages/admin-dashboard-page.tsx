import { PageHeader } from "@/components/shared/page-header";
import { KpiCards } from "../components/kpi-cards";
import { TeamBalanceChart } from "../components/team-balance-chart";
import { RequestStatusChart } from "../components/request-status-chart";
import { UsageByCategoryChart } from "../components/usage-by-category-chart";
import { useBalanceSummary } from "../hooks/use-reports";
import { useEmployees } from "@/features/employees/hooks/use-employees";
import { useRequests } from "@/features/requests/hooks/use-requests";
import { Skeleton } from "@/components/ui/skeleton";

export function AdminDashboardPage() {
  const { data: employees, isLoading: employeesLoading } = useEmployees();
  const { data: balanceSummary, isLoading: balancesLoading } = useBalanceSummary();
  const { data: requestsData, isLoading: requestsLoading } = useRequests();

  const isLoading = employeesLoading || balancesLoading || requestsLoading;

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Dashboard" subtitle="Company overview" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))}
        </div>
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-[350px] rounded-lg lg:col-span-2" />
          <Skeleton className="h-[350px] rounded-lg" />
        </div>
      </div>
    );
  }

  const pendingCount = requestsData?.items.filter((r) => r.status === "SUBMITTED").length ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" subtitle="Company overview" />

      <KpiCards employees={employees ?? []} balanceSummary={balanceSummary ?? []} pendingCount={pendingCount} />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <TeamBalanceChart balanceSummary={balanceSummary ?? []} employees={employees ?? []} />
        </div>
        <RequestStatusChart requests={requestsData?.items ?? []} />
      </div>

      <UsageByCategoryChart balanceSummary={balanceSummary ?? []} />
    </div>
  );
}
