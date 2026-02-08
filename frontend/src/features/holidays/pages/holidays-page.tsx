import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable } from "@/components/shared/data-table";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { AddHolidayDialog } from "../components/add-holiday-dialog";
import { useHolidays, useDeleteHoliday } from "../hooks/use-holidays";
import { useAuth } from "@/lib/auth/use-auth";
import type { Holiday } from "@/lib/api/types";
import { formatDate } from "@/lib/utils/format";
import { extractErrorMessage } from "@/lib/api/client";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";

const currentYear = new Date().getFullYear();
const yearOptions = [currentYear - 1, currentYear, currentYear + 1, currentYear + 2];

export function HolidaysPage() {
  const { role } = useAuth();
  const isAdmin = role === "admin";
  const [year, setYear] = useState<number>(currentYear);
  const { data, isLoading, isError, error } = useHolidays(year);
  const deleteHoliday = useDeleteHoliday();

  const handleDelete = (holidayId: string) => {
    deleteHoliday.mutate(holidayId, {
      onSuccess: () => toast.success("Holiday deleted"),
      onError: (err) => toast.error(extractErrorMessage(err)),
    });
  };

  const columns = useMemo<ColumnDef<Holiday, unknown>[]>(
    () => [
      {
        accessorKey: "date",
        header: "Date",
        cell: ({ row }) => formatDate(row.original.date),
      },
      {
        accessorKey: "name",
        header: "Name",
      },
      ...(isAdmin
        ? [
            {
              id: "actions",
              header: "Actions",
              cell: ({ row }: { row: { original: Holiday } }) => (
                <ConfirmDialog
                  trigger={
                    <Button variant="ghost" size="sm">
                      <Trash2 className="mr-1 h-3 w-3" />
                      Delete
                    </Button>
                  }
                  title="Delete holiday"
                  description={`Are you sure you want to delete "${row.original.name}"?`}
                  confirmLabel="Delete"
                  variant="destructive"
                  onConfirm={() => handleDelete(row.original.id)}
                  isPending={deleteHoliday.isPending}
                />
              ),
            } as ColumnDef<Holiday, unknown>,
          ]
        : []),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [isAdmin, deleteHoliday.isPending],
  );

  if (isError) {
    return (
      <div className="space-y-6">
        <PageHeader title="Company Holidays" />
        <div className="text-center text-destructive">{extractErrorMessage(error)}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Company Holidays"
        subtitle="Manage company-wide holidays"
        actions={
          <div className="flex items-center gap-2">
            <Select value={String(year)} onValueChange={(v) => setYear(Number(v))}>
              <SelectTrigger className="w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {yearOptions.map((y) => (
                  <SelectItem key={y} value={String(y)}>
                    {y}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {isAdmin && <AddHolidayDialog />}
          </div>
        }
      />

      {!isLoading && data?.items.length === 0 ? (
        <EmptyState title="No holidays" description={`No holidays configured for ${year}.`} />
      ) : (
        <DataTable
          columns={columns}
          data={data?.items ?? []}
          total={data?.total ?? 0}
          isLoading={isLoading}
          emptyMessage="No holidays found"
        />
      )}
    </div>
  );
}
