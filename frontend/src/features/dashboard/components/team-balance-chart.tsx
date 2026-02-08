import { useMemo } from "react";
import { Bar, BarChart, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
} from "@/components/ui/chart";
import type { ChartConfig } from "@/components/ui/chart";
import type { BalanceSummary, Employee } from "@/lib/api/types";
import { formatDuration } from "@/lib/utils/format";

interface TeamBalanceChartProps {
  balanceSummary: BalanceSummary[];
  employees: Employee[];
}

const chartConfig = {
  used: { label: "Used", color: "var(--chart-5)" },
  held: { label: "Held", color: "var(--chart-4)" },
  available: { label: "Available", color: "var(--chart-2)" },
} satisfies ChartConfig;

export function TeamBalanceChart({ balanceSummary, employees }: TeamBalanceChartProps) {
  const chartData = useMemo(() => {
    const employeeMap = new Map(employees.map((e) => [e.id, `${e.first_name} ${e.last_name}`]));

    // Group by employee, summing across policies (accrual only)
    const grouped = new Map<string, { used: number; held: number; available: number }>();
    for (const b of balanceSummary) {
      if (b.is_unlimited) continue;
      const existing = grouped.get(b.employee_id) ?? { used: 0, held: 0, available: 0 };
      existing.used += b.used_minutes;
      existing.held += b.held_minutes;
      existing.available += b.available_minutes ?? 0;
      grouped.set(b.employee_id, existing);
    }

    return Array.from(grouped.entries())
      .map(([id, data]) => ({
        name: employeeMap.get(id) ?? id.slice(-8),
        used: data.used / 480, // convert to days
        held: data.held / 480,
        available: data.available / 480,
      }))
      .sort((a, b) => b.used / (b.used + b.held + b.available || 1) - a.used / (a.used + a.held + a.available || 1));
  }, [balanceSummary, employees]);

  if (chartData.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Team Balances</CardTitle>
        <CardDescription>PTO usage across all employees (days)</CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className="h-[300px] w-full">
          <BarChart data={chartData} layout="vertical" margin={{ left: 0, right: 16 }}>
            <YAxis dataKey="name" type="category" width={100} tickLine={false} axisLine={false} className="text-xs" />
            <XAxis type="number" tickLine={false} axisLine={false} tickFormatter={(v) => `${v}d`} />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  formatter={(value, name) => (
                    <div className="flex items-center gap-2">
                      <span className="text-muted-foreground">
                        {chartConfig[name as keyof typeof chartConfig]?.label ?? name}
                      </span>
                      <span className="font-mono font-medium">
                        {formatDuration(Math.round((value as number) * 480), "DAYS")}
                      </span>
                    </div>
                  )}
                />
              }
            />
            <ChartLegend content={<ChartLegendContent />} />
            <Bar dataKey="used" stackId="a" fill="var(--color-used)" radius={[0, 0, 0, 0]} />
            <Bar dataKey="held" stackId="a" fill="var(--color-held)" radius={[0, 0, 0, 0]} />
            <Bar dataKey="available" stackId="a" fill="var(--color-available)" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ChartContainer>
      </CardContent>
    </Card>
  );
}
