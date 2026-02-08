import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable } from "@/components/shared/data-table";
import { EmptyState } from "@/components/shared/empty-state";
import { useAuditLog } from "../hooks/use-audit-log";
import { useEmployees } from "@/features/employees/hooks/use-employees";
import type { AuditLogEntry } from "@/lib/api/types";
import { formatDateTime, shortenId } from "@/lib/utils/format";
import { extractErrorMessage } from "@/lib/api/client";
import { Eye } from "lucide-react";

const ENTITY_TYPES = ["", "POLICY", "POLICY_VERSION", "ASSIGNMENT", "REQUEST", "EMPLOYEE", "HOLIDAY", "ADJUSTMENT"];
const ACTIONS = ["", "CREATE", "UPDATE", "DELETE", "SUBMIT", "APPROVE", "DENY", "CANCEL"];

export function AuditLogPage() {
  const [entityType, setEntityType] = useState("");
  const [action, setAction] = useState("");

  const filters = useMemo(() => {
    const f: Record<string, unknown> = {};
    if (entityType && entityType !== "all") f.entity_type = entityType;
    if (action && action !== "all") f.action = action;
    return f;
  }, [entityType, action]);

  const { data, isLoading, isError, error } = useAuditLog(Object.keys(filters).length > 0 ? filters : undefined);
  const { data: employees } = useEmployees();

  const employeeMap = useMemo(() => {
    const map = new Map<string, string>();
    employees?.forEach((e) => map.set(e.id, `${e.first_name} ${e.last_name}`));
    return map;
  }, [employees]);

  const columns = useMemo<ColumnDef<AuditLogEntry, unknown>[]>(
    () => [
      {
        accessorKey: "created_at",
        header: "Timestamp",
        cell: ({ row }) => <span className="text-xs whitespace-nowrap">{formatDateTime(row.original.created_at)}</span>,
      },
      {
        accessorKey: "actor_id",
        header: "Actor",
        cell: ({ row }) =>
          employeeMap.get(row.original.actor_id) ?? (
            <span className="font-mono text-xs">{shortenId(row.original.actor_id)}</span>
          ),
      },
      {
        accessorKey: "entity_type",
        header: "Entity Type",
        cell: ({ row }) => <span className="capitalize">{row.original.entity_type}</span>,
      },
      {
        accessorKey: "entity_id",
        header: "Entity ID",
        cell: ({ row }) => <span className="font-mono text-xs">{shortenId(row.original.entity_id)}</span>,
      },
      {
        accessorKey: "action",
        header: "Action",
        cell: ({ row }) => <span className="capitalize">{row.original.action}</span>,
      },
      {
        id: "details",
        header: "Details",
        cell: ({ row }) => <AuditDetailDialog entry={row.original} />,
      },
    ],
    [employeeMap],
  );

  if (isError) {
    return (
      <div className="space-y-6">
        <PageHeader title="Audit Log" />
        <div className="text-center text-destructive">{extractErrorMessage(error)}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Audit Log" subtitle="View system audit trail" />

      <div className="flex items-center gap-3">
        <Select value={entityType} onValueChange={setEntityType}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Entity type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All entities</SelectItem>
            {ENTITY_TYPES.filter(Boolean).map((t) => (
              <SelectItem key={t} value={t}>
                <span className="capitalize">{t.toLowerCase().replace("_", " ")}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={action} onValueChange={setAction}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Action" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All actions</SelectItem>
            {ACTIONS.filter(Boolean).map((a) => (
              <SelectItem key={a} value={a}>
                <span className="capitalize">{a.toLowerCase()}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {(entityType || action) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setEntityType("");
              setAction("");
            }}
          >
            Clear filters
          </Button>
        )}
      </div>

      {!isLoading && data?.items.length === 0 ? (
        <EmptyState title="No audit entries" description="No audit log entries match your filters." />
      ) : (
        <DataTable
          columns={columns}
          data={data?.items ?? []}
          total={data?.total ?? 0}
          isLoading={isLoading}
          emptyMessage="No audit entries found"
        />
      )}
    </div>
  );
}

function AuditDetailDialog({ entry }: { entry: AuditLogEntry }) {
  const hasBefore = entry.before_json && Object.keys(entry.before_json).length > 0;
  const hasAfter = entry.after_json && Object.keys(entry.after_json).length > 0;

  if (!hasBefore && !hasAfter) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm">
          <Eye className="mr-1 h-3 w-3" />
          View
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            Audit Detail — {entry.entity_type} / {entry.action}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {hasBefore && (
            <div>
              <h4 className="mb-1 text-sm font-medium">Before</h4>
              <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
                {JSON.stringify(entry.before_json, null, 2)}
              </pre>
            </div>
          )}
          {hasAfter && (
            <div>
              <h4 className="mb-1 text-sm font-medium">After</h4>
              <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
                {JSON.stringify(entry.after_json, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
