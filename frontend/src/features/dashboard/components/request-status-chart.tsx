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
import type { TimeOffRequest } from "@/lib/api/types";

interface RequestStatusChartProps {
  requests: TimeOffRequest[];
}

const STATUS_COLORS: Record<string, string> = {
  APPROVED: "var(--chart-2)",
  SUBMITTED: "var(--chart-4)",
  DENIED: "var(--chart-5)",
  CANCELLED: "var(--muted-foreground)",
};

const STATUS_LABELS: Record<string, string> = {
  APPROVED: "Approved",
  SUBMITTED: "Pending",
  DENIED: "Denied",
  CANCELLED: "Cancelled",
};

const chartConfig = {
  APPROVED: { label: "Approved", color: "var(--chart-2)" },
  SUBMITTED: { label: "Pending", color: "var(--chart-4)" },
  DENIED: { label: "Denied", color: "var(--chart-5)" },
  CANCELLED: { label: "Cancelled", color: "var(--muted-foreground)" },
} satisfies ChartConfig;

export function RequestStatusChart({ requests }: RequestStatusChartProps) {
  const chartData = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of requests) {
      if (r.status === "DRAFT") continue;
      counts[r.status] = (counts[r.status] || 0) + 1;
    }
    return Object.entries(counts)
      .filter(([, count]) => count > 0)
      .map(([status, count]) => ({
        name: status,
        value: count,
        fill: STATUS_COLORS[status] ?? "var(--chart-3)",
      }));
  }, [requests]);

  const total = useMemo(() => chartData.reduce((sum, d) => sum + d.value, 0), [chartData]);

  if (chartData.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Requests</CardTitle>
        <CardDescription>Request status breakdown</CardDescription>
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
                      <span className="text-muted-foreground">{STATUS_LABELS[name as string] ?? name}</span>
                      <span className="font-mono font-medium">{(value as number).toLocaleString()}</span>
                    </div>
                  )}
                />
              }
            />
            <Pie
              data={chartData}
              dataKey="value"
              nameKey="name"
              innerRadius={55}
              outerRadius={80}
              strokeWidth={2}
              stroke="var(--background)"
            >
              <Label
                content={({ viewBox }) => {
                  if (viewBox && "cx" in viewBox && "cy" in viewBox) {
                    return (
                      <text x={viewBox.cx} y={viewBox.cy} textAnchor="middle" dominantBaseline="middle">
                        <tspan x={viewBox.cx} y={(viewBox.cy || 0) - 4} className="fill-foreground text-xl font-bold">
                          {total}
                        </tspan>
                        <tspan x={viewBox.cx} y={(viewBox.cy || 0) + 14} className="fill-muted-foreground text-[10px]">
                          requests
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
