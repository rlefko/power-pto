import { Label, PolarGrid, PolarRadiusAxis, RadialBar, RadialBarChart } from "recharts";
import { ChartContainer } from "@/components/ui/chart";
import type { PolicyCategory } from "@/lib/api/types";
import { POLICY_CATEGORY_CHART_COLORS } from "@/lib/utils/constants";
import { formatDuration } from "@/lib/utils/format";

interface BalanceRadialChartProps {
  accrued: number;
  used: number;
  held: number;
  available: number;
  category: PolicyCategory;
}

export function BalanceRadialChart({ accrued, used, held, available, category }: BalanceRadialChartProps) {
  const fillColor = POLICY_CATEGORY_CHART_COLORS[category] ?? "var(--chart-1)";
  const usedPercent = accrued > 0 ? Math.min(((used + held) / accrued) * 100, 100) : 0;
  const availableLabel = formatDuration(available, "DAYS");
  // endAngle: full circle = 360°. We sweep from 90° (top) counterclockwise.
  // At 0% used, the arc fills the full ring (all available). At 100% used, no fill.
  const endAngle = 90 + (360 * (100 - usedPercent)) / 100;

  const chartData = [{ name: "balance", value: 100 - usedPercent, fill: fillColor }];

  const chartConfig = {
    balance: { label: "Available", color: fillColor },
  };

  return (
    <ChartContainer config={chartConfig} className="mx-auto aspect-square h-[140px] w-[140px]">
      <RadialBarChart data={chartData} startAngle={90} endAngle={endAngle} innerRadius={52} outerRadius={70}>
        <PolarGrid
          gridType="circle"
          radialLines={false}
          stroke="none"
          className="first:fill-muted last:fill-transparent"
        />
        <RadialBar dataKey="value" background cornerRadius={6} />
        <PolarRadiusAxis tick={false} tickLine={false} axisLine={false}>
          <Label
            content={({ viewBox }) => {
              if (viewBox && "cx" in viewBox && "cy" in viewBox) {
                return (
                  <text x={viewBox.cx} y={viewBox.cy} textAnchor="middle" dominantBaseline="middle">
                    <tspan x={viewBox.cx} y={(viewBox.cy || 0) - 4} className="fill-foreground text-lg font-bold">
                      {availableLabel}
                    </tspan>
                    <tspan x={viewBox.cx} y={(viewBox.cy || 0) + 14} className="fill-muted-foreground text-[10px]">
                      available
                    </tspan>
                  </text>
                );
              }
            }}
          />
        </PolarRadiusAxis>
      </RadialBarChart>
    </ChartContainer>
  );
}
