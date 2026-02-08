import { useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import type { TimeOffRequest, RequestStatus } from "@/lib/api/types";
import { REQUEST_STATUS_CONFIG } from "@/lib/utils/constants";

interface RequestStatusSummaryProps {
  requests: TimeOffRequest[];
}

const STATUS_ORDER: RequestStatus[] = ["APPROVED", "SUBMITTED", "DENIED", "CANCELLED"];

const STATUS_BORDER_COLORS: Record<RequestStatus, string> = {
  DRAFT: "border-l-muted-foreground",
  SUBMITTED: "border-l-amber-500",
  APPROVED: "border-l-emerald-500",
  DENIED: "border-l-red-500",
  CANCELLED: "border-l-gray-400",
};

export function RequestStatusSummary({ requests }: RequestStatusSummaryProps) {
  const counts = useMemo(() => {
    const map = new Map<RequestStatus, number>();
    for (const r of requests) {
      if (r.status === "DRAFT") continue;
      map.set(r.status, (map.get(r.status) || 0) + 1);
    }
    return map;
  }, [requests]);

  if (requests.length === 0) return null;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {STATUS_ORDER.map((status) => (
        <Card key={status} className={`border-l-4 ${STATUS_BORDER_COLORS[status]}`}>
          <CardContent className="px-4 py-3">
            <p className="text-2xl font-bold">{counts.get(status) ?? 0}</p>
            <p className="text-xs text-muted-foreground">{REQUEST_STATUS_CONFIG[status].label}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
