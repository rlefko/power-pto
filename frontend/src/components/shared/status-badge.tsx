import { Badge } from "@/components/ui/badge";
import type { RequestStatus } from "@/lib/api/types";
import { REQUEST_STATUS_CONFIG } from "@/lib/utils/constants";

interface StatusBadgeProps {
  status: RequestStatus;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const config = REQUEST_STATUS_CONFIG[status];
  return <Badge variant={config.variant}>{config.label}</Badge>;
}
