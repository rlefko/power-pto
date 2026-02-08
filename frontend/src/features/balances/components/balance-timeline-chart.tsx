import { useMemo } from "react";
import { Area, AreaChart, XAxis, YAxis, ReferenceLine } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import type { ChartConfig } from "@/components/ui/chart";
import { useEmployeeLedger } from "../hooks/use-balances";
import { LEDGER_ENTRY_TYPE_LABELS } from "@/lib/utils/constants";
import { formatDuration } from "@/lib/utils/format";
import { format, parseISO } from "date-fns";
import type { LedgerEntryType } from "@/lib/api/types";

interface BalanceTimelineChartProps {
  employeeId: string;
  policyId: string;
}

const chartConfig = {
  balance: { label: "Balance", color: "var(--chart-1)" },
} satisfies ChartConfig;

export function BalanceTimelineChart({ employeeId, policyId }: BalanceTimelineChartProps) {
  const { data, isLoading } = useEmployeeLedger(employeeId, policyId);

  const chartData = useMemo(() => {
    if (!data?.items?.length) return [];

    // Sort by effective_at ascending
    const sorted = [...data.items].sort(
      (a, b) => new Date(a.effective_at).getTime() - new Date(b.effective_at).getTime(),
    );

    let running = 0;
    return sorted.map((entry) => {
      running += entry.amount_minutes;
      return {
        date: format(parseISO(entry.effective_at), "MMM d"),
        balance: running / 480, // convert to days
        type: LEDGER_ENTRY_TYPE_LABELS[entry.entry_type as LedgerEntryType] ?? entry.entry_type,
        amount: entry.amount_minutes,
      };
    });
  }, [data]);

  if (isLoading || chartData.length === 0) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Balance Over Time</CardTitle>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className="h-[200px] w-full">
          <AreaChart data={chartData} margin={{ left: 0, right: 16, top: 4, bottom: 0 }}>
            <defs>
              <linearGradient id="balanceGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--color-balance)" stopOpacity={0.3} />
                <stop offset="95%" stopColor="var(--color-balance)" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <XAxis dataKey="date" tickLine={false} axisLine={false} className="text-xs" />
            <YAxis tickLine={false} axisLine={false} tickFormatter={(v) => `${v}d`} width={40} />
            <ReferenceLine y={0} stroke="var(--border)" strokeDasharray="3 3" />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  formatter={(value, _name, item) => {
                    const entry = item.payload;
                    return (
                      <div className="flex flex-col gap-0.5">
                        <div className="flex items-center gap-2">
                          <span className="text-muted-foreground">Balance</span>
                          <span className="font-mono font-medium">
                            {formatDuration(Math.round((value as number) * 480), "DAYS")}
                          </span>
                        </div>
                        <div className="text-[10px] text-muted-foreground">
                          {entry.type}: {entry.amount > 0 ? "+" : ""}
                          {formatDuration(entry.amount, "DAYS")}
                        </div>
                      </div>
                    );
                  }}
                />
              }
            />
            <Area
              type="stepAfter"
              dataKey="balance"
              stroke="var(--color-balance)"
              fill="url(#balanceGradient)"
              strokeWidth={2}
            />
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  );
}
