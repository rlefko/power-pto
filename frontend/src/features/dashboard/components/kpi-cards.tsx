import { useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Users, Clock, TrendingUp, CalendarCheck } from "lucide-react";
import type { Employee } from "@/lib/api/types";
import type { BalanceSummary } from "@/lib/api/types";
import { formatDuration } from "@/lib/utils/format";

interface KpiCardsProps {
  employees: Employee[];
  balanceSummary: BalanceSummary[];
  pendingCount: number;
}

export function KpiCards({ employees, balanceSummary, pendingCount }: KpiCardsProps) {
  const { totalUsed, avgUtilization } = useMemo(() => {
    const accrualBalances = balanceSummary.filter((b) => !b.is_unlimited && b.accrued_minutes > 0);
    const used = accrualBalances.reduce((sum, b) => sum + b.used_minutes, 0);

    let avg = 0;
    if (accrualBalances.length > 0) {
      const totalAcrrued = accrualBalances.reduce((sum, b) => sum + b.accrued_minutes, 0);
      avg = totalAcrrued > 0 ? Math.round((used / totalAcrrued) * 100) : 0;
    }

    return { totalUsed: used, avgUtilization: avg };
  }, [balanceSummary]);

  const cards = [
    {
      title: "Total Employees",
      value: employees.length.toString(),
      icon: Users,
    },
    {
      title: "Pending Approvals",
      value: pendingCount.toString(),
      icon: CalendarCheck,
    },
    {
      title: "Total PTO Used",
      value: formatDuration(totalUsed, "DAYS"),
      icon: Clock,
    },
    {
      title: "Avg Utilization",
      value: `${avgUtilization}%`,
      icon: TrendingUp,
    },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.title}>
          <CardContent className="flex items-center gap-4 pt-6">
            <div className="rounded-lg bg-muted p-2.5">
              <card.icon className="h-5 w-5 text-muted-foreground" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">{card.title}</p>
              <p className="text-2xl font-bold">{card.value}</p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
