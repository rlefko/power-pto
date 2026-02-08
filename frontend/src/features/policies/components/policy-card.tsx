import { Link } from "react-router";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CategoryBadge } from "@/components/shared/category-badge";
import type { Policy } from "@/lib/api/types";
import { POLICY_TYPE_LABELS, ACCRUAL_METHOD_LABELS } from "@/lib/utils/constants";
import { formatDate } from "@/lib/utils/format";

interface PolicyCardProps {
  policy: Policy;
}

export function PolicyCard({ policy }: PolicyCardProps) {
  const version = policy.current_version;
  return (
    <Link to={`/policies/${policy.id}`}>
      <Card className="transition-colors hover:bg-accent/50">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">{policy.key}</CardTitle>
            <CategoryBadge category={policy.category} />
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-1 text-sm text-muted-foreground">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-xs">
                {version ? POLICY_TYPE_LABELS[version.type] : "No version"}
              </Badge>
              {version?.accrual_method && (
                <Badge variant="secondary" className="text-xs">
                  {ACCRUAL_METHOD_LABELS[version.accrual_method]}
                </Badge>
              )}
            </div>
            {version && <span className="mt-1 text-xs">Effective from {formatDate(version.effective_from)}</span>}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
