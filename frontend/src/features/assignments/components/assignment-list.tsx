import { useMemo } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/shared/data-table";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import type { PolicyAssignment } from "@/lib/api/types";
import { formatDate, shortenId } from "@/lib/utils/format";
import { useAuth } from "@/lib/auth/use-auth";
import { useEmployees } from "@/features/employees/hooks/use-employees";
import { useAssignmentsByPolicy, useEndDateAssignment } from "../hooks/use-assignments";
import { toast } from "sonner";
import { extractErrorMessage } from "@/lib/api/client";
import { X } from "lucide-react";

interface AssignmentListProps {
  policyId: string;
}

export function AssignmentList({ policyId }: AssignmentListProps) {
  const { role } = useAuth();
  const isAdmin = role === "admin";
  const { data, isLoading } = useAssignmentsByPolicy(policyId);
  const { data: employees } = useEmployees();
  const endDateMutation = useEndDateAssignment();

  const employeeMap = useMemo(() => {
    const map = new Map<string, string>();
    employees?.forEach((e) => map.set(e.id, `${e.first_name} ${e.last_name}`));
    return map;
  }, [employees]);

  const handleEndDate = (assignmentId: string) => {
    endDateMutation.mutate(
      { assignmentId, effectiveTo: new Date().toISOString().split("T")[0] },
      {
        onSuccess: () => toast.success("Assignment end-dated"),
        onError: (err) => toast.error(extractErrorMessage(err)),
      },
    );
  };

  const columns: ColumnDef<PolicyAssignment, unknown>[] = [
    {
      accessorKey: "employee_id",
      header: "Employee",
      cell: ({ row }) => employeeMap.get(row.original.employee_id) ?? shortenId(row.original.employee_id),
    },
    {
      accessorKey: "effective_from",
      header: "Effective From",
      cell: ({ row }) => formatDate(row.original.effective_from),
    },
    {
      accessorKey: "effective_to",
      header: "Effective To",
      cell: ({ row }) => (row.original.effective_to ? formatDate(row.original.effective_to) : "—"),
    },
    ...(isAdmin
      ? [
          {
            id: "actions",
            header: "Actions",
            cell: ({ row }: { row: { original: PolicyAssignment } }) =>
              !row.original.effective_to ? (
                <ConfirmDialog
                  trigger={
                    <Button variant="outline" size="sm">
                      <X className="mr-1 h-3 w-3" />
                      End Date
                    </Button>
                  }
                  title="End-date assignment"
                  description="This will set today as the effective end date for this assignment. The employee will no longer accrue time under this policy."
                  confirmLabel="End Date"
                  variant="destructive"
                  onConfirm={() => handleEndDate(row.original.id)}
                  isPending={endDateMutation.isPending}
                />
              ) : null,
          } as ColumnDef<PolicyAssignment, unknown>,
        ]
      : []),
  ];

  if (!isLoading && data?.items.length === 0) {
    return <EmptyState title="No assignments" description="No employees are assigned to this policy yet." />;
  }

  return (
    <DataTable
      columns={columns}
      data={data?.items ?? []}
      total={data?.total ?? 0}
      isLoading={isLoading}
      emptyMessage="No assignments found"
    />
  );
}
