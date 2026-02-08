import { useMemo } from "react";
import { Bar, BarChart, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import type { ChartConfig } from "@/components/ui/chart";
import type { BalanceSummary, PolicyCategory } from "@/lib/api/types";
import { POLICY_CATEGORY_CONFIG, POLICY_CATEGORY_CHART_COLORS } from "@/lib/utils/constants";
import { formatDuration } from "@/lib/utils/format";

interface UsageByCategoryChartProps {
  balanceSummary: BalanceSummary[];
}

const chartConfig = {
  used: { label: "Used" },
} satisfies ChartConfig;

export function UsageByCategoryChart({ balanceSummary }: UsageByCategoryChartProps) {
  const chartData = useMemo(() => {
    const grouped = new Map<string, number>();
    for (const b of balanceSummary) {
      const cat = b.policy_category;
      grouped.set(cat, (grouped.get(cat) || 0) + b.used_minutes);
    }
    return Array.from(grouped.entries())
      .filter(([, used]) => used > 0)
      .map(([category, used]) => ({
        name: POLICY_CATEGORY_CONFIG[category as PolicyCategory]?.label ?? category,
        used: used / 480, // convert to days
        fill: POLICY_CATEGORY_CHART_COLORS[category as PolicyCategory] ?? "var(--chart-3)",
      }))
      .sort((a, b) => b.used - a.used);
  }, [balanceSummary]);

  if (chartData.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Usage by Category</CardTitle>
        <CardDescription>Total PTO used by policy type (days)</CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className="h-[250px] w-full">
          <BarChart data={chartData} margin={{ left: 0, right: 16 }}>
            <XAxis dataKey="name" tickLine={false} axisLine={false} className="text-xs" />
            <YAxis tickLine={false} axisLine={false} tickFormatter={(v) => `${v}d`} />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  hideLabel
                  formatter={(value) => (
                    <div className="flex items-center gap-2">
                      <span className="text-muted-foreground">Used</span>
                      <span className="font-mono font-medium">
                        {formatDuration(Math.round((value as number) * 480), "DAYS")}
                      </span>
                    </div>
                  )}
                />
              }
            />
            <Bar dataKey="used" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartContainer>
      </CardContent>
    </Card>
  );
}
