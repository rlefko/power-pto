import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { PolicyCreate, PolicyUpdate, PolicyCategory, PolicySettings, AccrualFrequency } from "@/lib/api/types";

type PolicyFormData = PolicyCreate | PolicyUpdate;

interface PolicyFormProps {
  mode: "create" | "edit";
  onSubmit: (data: PolicyFormData) => void;
  isPending?: boolean;
}

interface FormValues {
  key: string;
  category: PolicyCategory;
  effective_from: string;
  change_reason: string;
  type: "UNLIMITED" | "ACCRUAL";
  accrual_method: "TIME" | "HOURS_WORKED";
  accrual_frequency: AccrualFrequency;
  rate_minutes: number;
  accrue_minutes: number;
  per_worked_minutes: number;
  allow_negative: boolean;
  bank_cap_minutes: string;
}

export function PolicyForm({ mode, onSubmit, isPending }: PolicyFormProps) {
  const form = useForm<FormValues>({
    defaultValues: {
      key: "",
      category: "VACATION",
      effective_from: new Date().toISOString().split("T")[0],
      change_reason: "",
      type: "ACCRUAL",
      accrual_method: "TIME",
      accrual_frequency: "MONTHLY",
      rate_minutes: 800,
      accrue_minutes: 60,
      per_worked_minutes: 1440,
      allow_negative: false,
      bank_cap_minutes: "",
    },
  });

  const policyType = form.watch("type");
  const accrualMethod = form.watch("accrual_method");
  const accrualFrequency = form.watch("accrual_frequency");

  const handleSubmit = form.handleSubmit((values) => {
    let settings: PolicySettings;
    if (values.type === "UNLIMITED") {
      settings = { type: "UNLIMITED", unit: "DAYS" };
    } else if (values.accrual_method === "TIME") {
      const rateKey =
        values.accrual_frequency === "YEARLY"
          ? "rate_minutes_per_year"
          : values.accrual_frequency === "MONTHLY"
            ? "rate_minutes_per_month"
            : "rate_minutes_per_day";
      settings = {
        type: "ACCRUAL",
        accrual_method: "TIME",
        unit: "DAYS",
        accrual_frequency: values.accrual_frequency,
        accrual_timing: "END_OF_PERIOD",
        proration: "DAYS_ACTIVE",
        rate_minutes_per_year: rateKey === "rate_minutes_per_year" ? Number(values.rate_minutes) : null,
        rate_minutes_per_month: rateKey === "rate_minutes_per_month" ? Number(values.rate_minutes) : null,
        rate_minutes_per_day: rateKey === "rate_minutes_per_day" ? Number(values.rate_minutes) : null,
        allow_negative: values.allow_negative,
        negative_limit_minutes: null,
        bank_cap_minutes: values.bank_cap_minutes ? Number(values.bank_cap_minutes) : null,
        tenure_tiers: [],
        carryover: { enabled: false, cap_minutes: null, expires_after_days: null },
        expiration: {
          enabled: false,
          expires_after_days: null,
          expires_on_month: null,
          expires_on_day: null,
        },
      };
    } else {
      settings = {
        type: "ACCRUAL",
        accrual_method: "HOURS_WORKED",
        unit: "HOURS",
        accrual_ratio: {
          accrue_minutes: Number(values.accrue_minutes),
          per_worked_minutes: Number(values.per_worked_minutes),
        },
        allow_negative: values.allow_negative,
        negative_limit_minutes: null,
        bank_cap_minutes: values.bank_cap_minutes ? Number(values.bank_cap_minutes) : null,
        tenure_tiers: [],
        carryover: { enabled: false, cap_minutes: null, expires_after_days: null },
        expiration: {
          enabled: false,
          expires_after_days: null,
          expires_on_month: null,
          expires_on_day: null,
        },
      };
    }

    const version = {
      effective_from: values.effective_from,
      settings,
      change_reason: values.change_reason || null,
    };

    if (mode === "create") {
      onSubmit({
        key: values.key,
        category: values.category,
        version,
      });
    } else {
      onSubmit({ version });
    }
  });

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {mode === "create" && (
        <>
          <div className="space-y-2">
            <Label htmlFor="key">Policy Key</Label>
            <Input id="key" placeholder="e.g., vacation-ft" {...form.register("key", { required: true })} />
          </div>
          <div className="space-y-2">
            <Label>Category</Label>
            <Select
              value={form.watch("category")}
              onValueChange={(v) => form.setValue("category", v as PolicyCategory)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="VACATION">Vacation</SelectItem>
                <SelectItem value="SICK">Sick</SelectItem>
                <SelectItem value="PERSONAL">Personal</SelectItem>
                <SelectItem value="BEREAVEMENT">Bereavement</SelectItem>
                <SelectItem value="PARENTAL">Parental</SelectItem>
                <SelectItem value="OTHER">Other</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </>
      )}

      <div className="space-y-2">
        <Label htmlFor="effective_from">Effective From</Label>
        <Input id="effective_from" type="date" {...form.register("effective_from", { required: true })} />
      </div>

      <div className="space-y-2">
        <Label>Policy Type</Label>
        <Select value={policyType} onValueChange={(v) => form.setValue("type", v as "UNLIMITED" | "ACCRUAL")}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ACCRUAL">Accrual</SelectItem>
            <SelectItem value="UNLIMITED">Unlimited</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {policyType === "ACCRUAL" && (
        <>
          <div className="space-y-2">
            <Label>Accrual Method</Label>
            <Select
              value={accrualMethod}
              onValueChange={(v) => form.setValue("accrual_method", v as "TIME" | "HOURS_WORKED")}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="TIME">Time-Based</SelectItem>
                <SelectItem value="HOURS_WORKED">Hours Worked</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {accrualMethod === "TIME" && (
            <>
              <div className="space-y-2">
                <Label>Frequency</Label>
                <Select
                  value={accrualFrequency}
                  onValueChange={(v) => form.setValue("accrual_frequency", v as AccrualFrequency)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="DAILY">Daily</SelectItem>
                    <SelectItem value="MONTHLY">Monthly</SelectItem>
                    <SelectItem value="YEARLY">Yearly</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="rate_minutes">Rate (minutes per {accrualFrequency.toLowerCase()} period)</Label>
                <Input id="rate_minutes" type="number" {...form.register("rate_minutes", { required: true, min: 1 })} />
              </div>
            </>
          )}

          {accrualMethod === "HOURS_WORKED" && (
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="accrue_minutes">Accrue (minutes)</Label>
                <Input
                  id="accrue_minutes"
                  type="number"
                  {...form.register("accrue_minutes", { required: true, min: 1 })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="per_worked_minutes">Per worked (minutes)</Label>
                <Input
                  id="per_worked_minutes"
                  type="number"
                  {...form.register("per_worked_minutes", { required: true, min: 1 })}
                />
              </div>
            </div>
          )}

          <div className="flex items-center gap-2">
            <Switch
              id="allow_negative"
              checked={form.watch("allow_negative")}
              onCheckedChange={(v) => form.setValue("allow_negative", v)}
            />
            <Label htmlFor="allow_negative">Allow Negative Balance</Label>
          </div>

          <div className="space-y-2">
            <Label htmlFor="bank_cap_minutes">Bank Cap (minutes, optional)</Label>
            <Input id="bank_cap_minutes" type="number" placeholder="No cap" {...form.register("bank_cap_minutes")} />
          </div>
        </>
      )}

      <div className="space-y-2">
        <Label htmlFor="change_reason">Change Reason</Label>
        <Textarea id="change_reason" placeholder="Optional" {...form.register("change_reason")} />
      </div>

      <Button type="submit" className="w-full" disabled={isPending}>
        {isPending ? "Saving..." : mode === "create" ? "Create Policy" : "Update Policy"}
      </Button>
    </form>
  );
}
