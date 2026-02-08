import type {
  AccrualFrequency,
  AccrualMethod,
  LedgerEntryType,
  PolicyCategory,
  PolicyType,
  RequestStatus,
} from "@/lib/api/types";

export const REQUEST_STATUS_CONFIG: Record<
  RequestStatus,
  { label: string; variant: "default" | "secondary" | "destructive" | "outline" }
> = {
  DRAFT: { label: "Draft", variant: "secondary" },
  SUBMITTED: { label: "Pending", variant: "outline" },
  APPROVED: { label: "Approved", variant: "default" },
  DENIED: { label: "Denied", variant: "destructive" },
  CANCELLED: { label: "Cancelled", variant: "secondary" },
};

export const POLICY_CATEGORY_CONFIG: Record<PolicyCategory, { label: string; className: string }> = {
  VACATION: {
    label: "Vacation",
    className: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  },
  SICK: {
    label: "Sick",
    className: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  },
  PERSONAL: {
    label: "Personal",
    className: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
  },
  BEREAVEMENT: {
    label: "Bereavement",
    className: "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200",
  },
  PARENTAL: {
    label: "Parental",
    className: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  },
  OTHER: {
    label: "Other",
    className: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  },
};

export const POLICY_TYPE_LABELS: Record<PolicyType, string> = {
  UNLIMITED: "Unlimited",
  ACCRUAL: "Accrual",
};

export const ACCRUAL_METHOD_LABELS: Record<AccrualMethod, string> = {
  TIME: "Time-Based",
  HOURS_WORKED: "Hours Worked",
};

export const ACCRUAL_FREQUENCY_LABELS: Record<AccrualFrequency, string> = {
  DAILY: "Daily",
  MONTHLY: "Monthly",
  YEARLY: "Yearly",
};

export const POLICY_CATEGORY_CHART_COLORS: Record<PolicyCategory, string> = {
  VACATION: "var(--chart-1)",
  SICK: "var(--chart-5)",
  PERSONAL: "var(--chart-4)",
  BEREAVEMENT: "var(--muted-foreground)",
  PARENTAL: "var(--chart-2)",
  OTHER: "var(--chart-3)",
};

export const LEDGER_ENTRY_TYPE_LABELS: Record<LedgerEntryType, string> = {
  ACCRUAL: "Accrual",
  HOLD: "Hold",
  HOLD_RELEASE: "Hold Release",
  USAGE: "Usage",
  ADJUSTMENT: "Adjustment",
  EXPIRATION: "Expiration",
  CARRYOVER: "Carryover",
};
