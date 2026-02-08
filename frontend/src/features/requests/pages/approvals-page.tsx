import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable } from "@/components/shared/data-table";
import { EmptyState } from "@/components/shared/empty-state";
import { DecisionDialog } from "../components/decision-dialog";
import { useRequests } from "../hooks/use-requests";
import { useEmployees } from "@/features/employees/hooks/use-employees";
import { usePolicies } from "@/features/policies/hooks/use-policies";
import type { TimeOffRequest } from "@/lib/api/types";
import { formatDateRange, formatDuration, shortenId } from "@/lib/utils/format";
import { extractErrorMessage } from "@/lib/api/client";
import { Check, X } from "lucide-react";

export function ApprovalsPage() {
  const filters = useMemo(() => ({ status: "SUBMITTED" }), []);
  const { data, isLoading, isError, error } = useRequests(filters);
  const { data: employees } = useEmployees();
  const { data: policiesData } = usePolicies();

  const employeeMap = useMemo(() => {
    const map = new Map<string, string>();
    employees?.forEach((e) => map.set(e.id, `${e.first_name} ${e.last_name}`));
    return map;
  }, [employees]);

  const policyMap = useMemo(() => {
    const map = new Map<string, string>();
    policiesData?.items.forEach((p) => map.set(p.id, p.key));
    return map;
  }, [policiesData]);

  const columns = useMemo<ColumnDef<TimeOffRequest, unknown>[]>(
    () => [
      {
        accessorKey: "employee_id",
        header: "Employee",
        cell: ({ row }) => employeeMap.get(row.original.employee_id) ?? shortenId(row.original.employee_id),
      },
      {
        accessorKey: "policy_id",
        header: "Policy",
        cell: ({ row }) => policyMap.get(row.original.policy_id) ?? shortenId(row.original.policy_id),
      },
      {
        id: "date_range",
        header: "Date Range",
        cell: ({ row }) => formatDateRange(row.original.start_at, row.original.end_at),
      },
      {
        accessorKey: "requested_minutes",
        header: "Duration",
        cell: ({ row }) => formatDuration(row.original.requested_minutes, "DAYS"),
      },
      {
        accessorKey: "reason",
        header: "Reason",
        cell: ({ row }) => {
          const reason = row.original.reason;
          if (!reason) return <span className="text-muted-foreground">—</span>;
          return reason.length > 50 ? `${reason.slice(0, 50)}...` : reason;
        },
      },
      {
        id: "actions",
        header: "Actions",
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            <DecisionDialog
              requestId={row.original.id}
              variant="approve"
              trigger={
                <Button variant="ghost" size="sm">
                  <Check className="mr-1 h-3 w-3" />
                  Approve
                </Button>
              }
            />
            <DecisionDialog
              requestId={row.original.id}
              variant="deny"
              trigger={
                <Button variant="ghost" size="sm">
                  <X className="mr-1 h-3 w-3" />
                  Deny
                </Button>
              }
            />
          </div>
        ),
      },
    ],
    [employeeMap, policyMap],
  );

  if (isError) {
    return (
      <div className="space-y-6">
        <PageHeader title="Pending Approvals" />
        <div className="text-center text-destructive">{extractErrorMessage(error)}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Pending Approvals" subtitle="Review and decide on time-off requests" />

      {!isLoading && data?.items.length === 0 ? (
        <EmptyState title="No pending requests" description="All time-off requests have been reviewed." />
      ) : (
        <DataTable
          columns={columns}
          data={data?.items ?? []}
          total={data?.total ?? 0}
          isLoading={isLoading}
          emptyMessage="No pending requests"
        />
      )}
    </div>
  );
}
