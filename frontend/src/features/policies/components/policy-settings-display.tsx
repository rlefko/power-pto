import type { PolicySettings } from "@/lib/api/types";
import { Separator } from "@/components/ui/separator";
import { formatDuration } from "@/lib/utils/format";
import { ACCRUAL_FREQUENCY_LABELS } from "@/lib/utils/constants";

interface PolicySettingsDisplayProps {
  settings: PolicySettings;
}

export function PolicySettingsDisplay({ settings }: PolicySettingsDisplayProps) {
  if (settings.type === "UNLIMITED") {
    return (
      <div className="space-y-4">
        <SettingRow label="Type" value="Unlimited" />
        <SettingRow label="Display Unit" value={settings.unit} />
      </div>
    );
  }

  const isTime = settings.accrual_method === "TIME";

  return (
    <div className="space-y-4">
      <SettingRow label="Type" value="Accrual" />
      <SettingRow label="Method" value={isTime ? "Time-Based" : "Hours Worked"} />
      <SettingRow label="Display Unit" value={settings.unit} />
      <Separator />

      {isTime && (
        <>
          <SettingRow label="Frequency" value={ACCRUAL_FREQUENCY_LABELS[settings.accrual_frequency]} />
          {settings.rate_minutes_per_year != null && (
            <SettingRow label="Rate (per year)" value={formatDuration(settings.rate_minutes_per_year, settings.unit)} />
          )}
          {settings.rate_minutes_per_month != null && (
            <SettingRow
              label="Rate (per month)"
              value={formatDuration(settings.rate_minutes_per_month, settings.unit)}
            />
          )}
          {settings.rate_minutes_per_day != null && (
            <SettingRow label="Rate (per day)" value={formatDuration(settings.rate_minutes_per_day, settings.unit)} />
          )}
          <SettingRow label="Timing" value={settings.accrual_timing.replace(/_/g, " ").toLowerCase()} />
          <SettingRow label="Proration" value={settings.proration.replace(/_/g, " ").toLowerCase()} />
        </>
      )}

      {!isTime && (
        <SettingRow
          label="Accrual Ratio"
          value={`${settings.accrual_ratio.accrue_minutes} min per ${settings.accrual_ratio.per_worked_minutes} min worked`}
        />
      )}

      <Separator />
      <SettingRow label="Allow Negative" value={settings.allow_negative ? "Yes" : "No"} />
      {settings.negative_limit_minutes != null && (
        <SettingRow label="Negative Limit" value={formatDuration(settings.negative_limit_minutes, settings.unit)} />
      )}
      {settings.bank_cap_minutes != null && (
        <SettingRow label="Bank Cap" value={formatDuration(settings.bank_cap_minutes, settings.unit)} />
      )}

      {settings.tenure_tiers.length > 0 && (
        <>
          <Separator />
          <div>
            <span className="text-sm font-medium">Tenure Tiers</span>
            <div className="mt-2 space-y-1">
              {settings.tenure_tiers.map((tier, i) => (
                <div key={i} className="text-sm text-muted-foreground">
                  After {tier.min_months} months: {formatDuration(tier.accrual_rate_minutes, settings.unit)}
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {settings.carryover.enabled && (
        <>
          <Separator />
          <SettingRow label="Carryover" value="Enabled" />
          {settings.carryover.cap_minutes != null && (
            <SettingRow label="Carryover Cap" value={formatDuration(settings.carryover.cap_minutes, settings.unit)} />
          )}
          {settings.carryover.expires_after_days != null && (
            <SettingRow label="Carryover Expires" value={`After ${settings.carryover.expires_after_days} days`} />
          )}
        </>
      )}

      {settings.expiration.enabled && (
        <>
          <Separator />
          <SettingRow label="Expiration" value="Enabled" />
          {settings.expiration.expires_after_days != null && (
            <SettingRow label="Expires After" value={`${settings.expiration.expires_after_days} days`} />
          )}
          {settings.expiration.expires_on_month != null && settings.expiration.expires_on_day != null && (
            <SettingRow
              label="Expires On"
              value={`${settings.expiration.expires_on_month}/${settings.expiration.expires_on_day}`}
            />
          )}
        </>
      )}
    </div>
  );
}

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium capitalize">{value}</span>
    </div>
  );
}
