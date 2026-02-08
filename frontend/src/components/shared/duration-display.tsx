import type { DisplayUnit } from "@/lib/api/types";
import { formatDuration } from "@/lib/utils/format";

interface DurationDisplayProps {
  minutes: number;
  unit?: DisplayUnit;
  workdayMinutes?: number;
}

export function DurationDisplay({ minutes, unit = "DAYS", workdayMinutes = 480 }: DurationDisplayProps) {
  return <span>{formatDuration(minutes, unit, workdayMinutes)}</span>;
}
