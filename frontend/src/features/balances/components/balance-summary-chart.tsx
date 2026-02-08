import { useMemo } from "react";
import { Label, Pie, PieChart } from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
} from "@/components/ui/chart";
import type { ChartConfig } from "@/components/ui/chart";
import type { EmployeeBalance, PolicyCategory } from "@/lib/api/types";
import { POLICY_CATEGORY_CHART_COLORS, POLICY_CATEGORY_CONFIG } from "@/lib/utils/constants";
import { formatDuration } from "@/lib/utils/format";

interface BalanceSummaryChartProps {
  balances: EmployeeBalance[];
}

export function BalanceSummaryChart({ balances }: BalanceSummaryChartProps) {
  const accrualBalances = useMemo(() => balances.filter((b) => !b.is_unlimited && b.accrued_minutes > 0), [balances]);

  const chartData = useMemo(
    () =>
      accrualBalances.map((b) => ({
        name: b.policy_key,
        value: b.accrued_minutes,
        fill: POLICY_CATEGORY_CHART_COLORS[b.policy_category as PolicyCategory] ?? "var(--chart-3)",
      })),
    [accrualBalances],
  );

  const chartConfig = useMemo(() => {
    const config: ChartConfig = {};
    accrualBalances.forEach((b) => {
      config[b.policy_key] = {
        label: POLICY_CATEGORY_CONFIG[b.policy_category as PolicyCategory]?.label ?? b.policy_key,
        color: POLICY_CATEGORY_CHART_COLORS[b.policy_category as PolicyCategory] ?? "var(--chart-3)",
      };
    });
    return config;
  }, [accrualBalances]);

  const totalAvailable = useMemo(
    () => accrualBalances.reduce((sum, b) => sum + (b.available_minutes ?? 0), 0),
    [accrualBalances],
  );

  if (accrualBalances.length === 0) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Time-Off Overview</CardTitle>
        <CardDescription>Your total allocation across all policies</CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className="mx-auto aspect-square h-[220px] w-[220px]">
          <PieChart>
            <ChartTooltip
              content={
                <ChartTooltipContent
                  hideLabel
                  formatter={(value, name) => (
                    <div className="flex items-center gap-2">
                      <span className="text-muted-foreground">{name}</span>
                      <span className="font-mono font-medium">{formatDuration(value as number, "DAYS")}</span>
                    </div>
                  )}
                />
              }
            />
            <Pie
              data={chartData}
              dataKey="value"
              nameKey="name"
              innerRadius={60}
              outerRadius={85}
              strokeWidth={2}
              stroke="var(--background)"
            >
              <Label
                content={({ viewBox }) => {
                  if (viewBox && "cx" in viewBox && "cy" in viewBox) {
                    return (
                      <text x={viewBox.cx} y={viewBox.cy} textAnchor="middle" dominantBaseline="middle">
                        <tspan x={viewBox.cx} y={(viewBox.cy || 0) - 4} className="fill-foreground text-xl font-bold">
                          {formatDuration(totalAvailable, "DAYS")}
                        </tspan>
                        <tspan x={viewBox.cx} y={(viewBox.cy || 0) + 14} className="fill-muted-foreground text-[10px]">
                          available
                        </tspan>
                      </text>
                    );
                  }
                }}
              />
            </Pie>
            <ChartLegend content={<ChartLegendContent nameKey="name" />} />
          </PieChart>
        </ChartContainer>
      </CardContent>
    </Card>
  );
}
