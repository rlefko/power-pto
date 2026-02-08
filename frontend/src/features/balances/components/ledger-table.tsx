import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";
import { DataTable } from "@/components/shared/data-table";
import { DurationDisplay } from "@/components/shared/duration-display";
import { useEmployeeLedger } from "../hooks/use-balances";
import type { LedgerEntry } from "@/lib/api/types";
import { formatDateTime, shortenId } from "@/lib/utils/format";
import { LEDGER_ENTRY_TYPE_LABELS } from "@/lib/utils/constants";

interface LedgerTableProps {
  employeeId: string;
  policyId: string;
}

export function LedgerTable({ employeeId, policyId }: LedgerTableProps) {
  const { data, isLoading } = useEmployeeLedger(employeeId, policyId);

  const columns = useMemo<ColumnDef<LedgerEntry, unknown>[]>(
    () => [
      {
        accessorKey: "entry_type",
        header: "Type",
        cell: ({ row }) => (
          <Badge variant="outline">
            {LEDGER_ENTRY_TYPE_LABELS[row.original.entry_type] ?? row.original.entry_type}
          </Badge>
        ),
      },
      {
        accessorKey: "amount_minutes",
        header: "Amount",
        cell: ({ row }) => {
          const minutes = row.original.amount_minutes;
          const sign = minutes >= 0 ? "+" : "";
          return (
            <span className={minutes >= 0 ? "text-green-600" : "text-red-600"}>
              {sign}
              <DurationDisplay minutes={minutes} />
            </span>
          );
        },
      },
      {
        accessorKey: "effective_at",
        header: "Effective At",
        cell: ({ row }) => formatDateTime(row.original.effective_at),
      },
      {
        accessorKey: "source_type",
        header: "Source",
        cell: ({ row }) => <span className="capitalize">{row.original.source_type.toLowerCase()}</span>,
      },
      {
        accessorKey: "source_id",
        header: "Source ID",
        cell: ({ row }) => <span className="font-mono text-xs">{shortenId(row.original.source_id)}</span>,
      },
      {
        accessorKey: "created_at",
        header: "Created",
        cell: ({ row }) => formatDateTime(row.original.created_at),
      },
    ],
    [],
  );

  return (
    <DataTable
      columns={columns}
      data={data?.items ?? []}
      total={data?.total ?? 0}
      isLoading={isLoading}
      emptyMessage="No ledger entries"
    />
  );
}
