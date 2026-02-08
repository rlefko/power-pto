import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/shared/data-table";
import type { PolicyVersion } from "@/lib/api/types";
import { POLICY_TYPE_LABELS } from "@/lib/utils/constants";
import { formatDate, formatDateTime } from "@/lib/utils/format";

const columns: ColumnDef<PolicyVersion>[] = [
  {
    accessorKey: "version",
    header: "Version",
    cell: ({ row }) => `v${row.original.version}`,
  },
  {
    accessorKey: "effective_from",
    header: "Effective From",
    cell: ({ row }) => formatDate(row.original.effective_from),
  },
  {
    accessorKey: "effective_to",
    header: "Effective To",
    cell: ({ row }) => (row.original.effective_to ? formatDate(row.original.effective_to) : "Current"),
  },
  {
    accessorKey: "type",
    header: "Type",
    cell: ({ row }) => POLICY_TYPE_LABELS[row.original.type],
  },
  {
    accessorKey: "change_reason",
    header: "Change Reason",
    cell: ({ row }) => row.original.change_reason ?? "\u2014",
  },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => formatDateTime(row.original.created_at),
  },
];

interface PolicyVersionListProps {
  versions: PolicyVersion[];
  total: number;
  isLoading?: boolean;
}

export function PolicyVersionList({ versions, total, isLoading }: PolicyVersionListProps) {
  return (
    <DataTable columns={columns} data={versions} total={total} isLoading={isLoading} emptyMessage="No versions found" />
  );
}
