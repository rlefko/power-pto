import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CategoryBadge } from "@/components/shared/category-badge";
import { DurationDisplay } from "@/components/shared/duration-display";
import { BalanceRadialChart } from "./balance-radial-chart";
import type { EmployeeBalance, PolicyCategory } from "@/lib/api/types";

interface BalanceCardProps {
  balance: EmployeeBalance;
}

export function BalanceCard({ balance }: BalanceCardProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{balance.policy_key}</CardTitle>
          <CategoryBadge category={balance.policy_category as PolicyCategory} />
        </div>
      </CardHeader>
      <CardContent>
        {balance.is_unlimited ? (
          <div className="space-y-1 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Type</span>
              <span className="font-medium">Unlimited</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Used</span>
              <span className="font-medium">
                <DurationDisplay minutes={balance.used_minutes} />
              </span>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <BalanceRadialChart
              accrued={balance.accrued_minutes}
              used={balance.used_minutes}
              held={balance.held_minutes}
              available={balance.available_minutes ?? 0}
              category={balance.policy_category as PolicyCategory}
            />
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Accrued</span>
                <span className="font-medium">
                  <DurationDisplay minutes={balance.accrued_minutes} />
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Used</span>
                <span className="font-medium">
                  <DurationDisplay minutes={balance.used_minutes} />
                </span>
              </div>
              {balance.held_minutes > 0 && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Held</span>
                  <span className="font-medium">
                    <DurationDisplay minutes={balance.held_minutes} />
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
