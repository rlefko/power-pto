import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable } from "@/components/shared/data-table";
import { EmptyState } from "@/components/shared/empty-state";
import { DecisionDialog } from "../components/decision-dialog";
import { useRequests } from "../hooks/use-requests";
import type { TimeOffRequest } from "@/lib/api/types";
import { formatDateRange, formatDuration } from "@/lib/utils/format";
import { extractErrorMessage } from "@/lib/api/client";
import { Check, X } from "lucide-react";

export function ApprovalsPage() {
  const filters = useMemo(() => ({ status: "SUBMITTED" }), []);
  const { data, isLoading, isError, error } = useRequests(filters);

  const columns = useMemo<ColumnDef<TimeOffRequest, unknown>[]>(
    () => [
      {
        accessorKey: "employee_id",
        header: "Employee",
        cell: ({ row }) => <span className="font-mono text-xs">{row.original.employee_id.slice(0, 8)}</span>,
      },
      {
        accessorKey: "policy_id",
        header: "Policy",
        cell: ({ row }) => <span className="font-mono text-xs">{row.original.policy_id.slice(0, 8)}</span>,
      },
      {
        id: "date_range",
        header: "Date Range",
        cell: ({ row }) => formatDateRange(row.original.start_at, row.original.end_at),
      },
      {
        accessorKey: "requested_minutes",
        header: "Duration",
        cell: ({ row }) => formatDuration(row.original.requested_minutes),
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
    [],
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
