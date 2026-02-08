import { useCallback, useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable } from "@/components/shared/data-table";
import { StatusBadge } from "@/components/shared/status-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { SubmitRequestDialog } from "../components/submit-request-dialog";
import { RequestStatusSummary } from "../components/request-status-summary";
import { useRequests, useCancelRequest } from "../hooks/use-requests";
import { usePolicies } from "@/features/policies/hooks/use-policies";
import { useAuth } from "@/lib/auth/use-auth";
import type { RequestStatus, TimeOffRequest } from "@/lib/api/types";
import { formatDateRange, formatDuration, shortenId } from "@/lib/utils/format";
import { toast } from "sonner";
import { extractErrorMessage } from "@/lib/api/client";
import { Plus, X } from "lucide-react";

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "ALL", label: "All Statuses" },
  { value: "SUBMITTED", label: "Pending" },
  { value: "APPROVED", label: "Approved" },
  { value: "DENIED", label: "Denied" },
  { value: "CANCELLED", label: "Cancelled" },
];

export function MyRequestsPage() {
  const { userId } = useAuth();
  const [statusFilter, setStatusFilter] = useState("ALL");
  const cancelRequest = useCancelRequest();

  const filters = useMemo(() => {
    const f: Record<string, string> = { employee_id: userId };
    if (statusFilter !== "ALL") {
      f.status = statusFilter;
    }
    return f;
  }, [userId, statusFilter]);

  const allFilters = useMemo(() => ({ employee_id: userId }), [userId]);
  const { data: allRequestsData } = useRequests(allFilters);
  const { data, isLoading, isError, error } = useRequests(filters);
  const { data: policiesData } = usePolicies();

  const policyMap = useMemo(() => {
    const map = new Map<string, string>();
    policiesData?.items.forEach((p) => map.set(p.id, p.key));
    return map;
  }, [policiesData]);

  const handleCancel = useCallback(
    (requestId: string) => {
      cancelRequest.mutate(requestId, {
        onSuccess: () => toast.success("Request cancelled"),
        onError: (err) => toast.error(extractErrorMessage(err)),
      });
    },
    [cancelRequest],
  );

  const columns = useMemo<ColumnDef<TimeOffRequest, unknown>[]>(
    () => [
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => <StatusBadge status={row.original.status as RequestStatus} />,
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
        cell: ({ row }) => {
          if (row.original.status !== "SUBMITTED") return null;
          return (
            <ConfirmDialog
              trigger={
                <Button variant="ghost" size="sm">
                  <X className="mr-1 h-3 w-3" />
                  Cancel
                </Button>
              }
              title="Cancel Request"
              description="Are you sure you want to cancel this time-off request? This action cannot be undone."
              confirmLabel="Cancel Request"
              variant="destructive"
              onConfirm={() => handleCancel(row.original.id)}
              isPending={cancelRequest.isPending}
            />
          );
        },
      },
    ],
    [handleCancel, cancelRequest.isPending, policyMap],
  );

  if (isError) {
    return (
      <div className="space-y-6">
        <PageHeader title="My Requests" />
        <div className="text-center text-destructive">{extractErrorMessage(error)}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Requests"
        subtitle="View and manage your time-off requests"
        actions={
          <SubmitRequestDialog
            trigger={
              <Button size="sm">
                <Plus className="mr-1 h-4 w-4" />
                Request Time Off
              </Button>
            }
          />
        }
      />

      {allRequestsData?.items && allRequestsData.items.length > 0 && (
        <RequestStatusSummary requests={allRequestsData.items} />
      )}

      <div className="flex items-center gap-4">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {!isLoading && data?.items.length === 0 ? (
        <EmptyState title="No requests yet" description="Submit a time-off request to get started." />
      ) : (
        <DataTable
          columns={columns}
          data={data?.items ?? []}
          total={data?.total ?? 0}
          isLoading={isLoading}
          emptyMessage="No requests found"
        />
      )}
    </div>
  );
}
