import { format, parseISO } from "date-fns";
import type { DisplayUnit } from "@/lib/api/types";

const DEFAULT_WORKDAY_MINUTES = 480;

export function formatDuration(
  minutes: number,
  unit?: DisplayUnit,
  workdayMinutes: number = DEFAULT_WORKDAY_MINUTES,
): string {
  if (minutes === 0) {
    switch (unit) {
      case "DAYS":
        return "0 days";
      case "HOURS":
        return "0 hours";
      default:
        return "0 minutes";
    }
  }

  switch (unit) {
    case "DAYS": {
      const days = minutes / workdayMinutes;
      const formatted = Number.isInteger(days) ? days.toString() : days.toFixed(1);
      return `${formatted} day${days === 1 ? "" : "s"}`;
    }
    case "HOURS": {
      const hours = minutes / 60;
      const formatted = Number.isInteger(hours) ? hours.toString() : hours.toFixed(1);
      return `${formatted} hour${hours === 1 ? "" : "s"}`;
    }
    default: {
      return `${minutes} minute${minutes === 1 ? "" : "s"}`;
    }
  }
}

export function shortenId(uuid: string): string {
  return uuid.replace(/-/g, "").slice(-8);
}

export function formatDate(isoString: string): string {
  return format(parseISO(isoString), "MMM d, yyyy");
}

export function formatDateTime(isoString: string): string {
  return format(parseISO(isoString), "MMM d, yyyy, h:mm a");
}

export function formatDateRange(start: string, end: string): string {
  const startDate = parseISO(start);
  const endDate = parseISO(end);

  const startYear = startDate.getFullYear();
  const endYear = endDate.getFullYear();

  if (startYear === endYear) {
    return `${format(startDate, "MMM d")} \u2013 ${format(endDate, "MMM d, yyyy")}`;
  }

  return `${format(startDate, "MMM d, yyyy")} \u2013 ${format(endDate, "MMM d, yyyy")}`;
}
