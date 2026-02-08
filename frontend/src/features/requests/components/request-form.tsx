import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/lib/auth/use-auth";
import { useEmployeeBalances } from "../hooks/use-requests";
import type { TimeOffRequestCreate } from "@/lib/api/types";

interface RequestFormProps {
  onSubmit: (data: TimeOffRequestCreate) => void;
  isPending?: boolean;
}

interface FormValues {
  policy_id: string;
  start_at: string;
  end_at: string;
  reason: string;
}

export function RequestForm({ onSubmit, isPending }: RequestFormProps) {
  const { userId } = useAuth();
  const { data: balances, isLoading: balancesLoading } = useEmployeeBalances(userId);

  const form = useForm<FormValues>({
    defaultValues: {
      policy_id: "",
      start_at: "",
      end_at: "",
      reason: "",
    },
  });

  const handleSubmit = form.handleSubmit((values) => {
    onSubmit({
      employee_id: userId,
      policy_id: values.policy_id,
      start_at: new Date(values.start_at).toISOString(),
      end_at: new Date(values.end_at).toISOString(),
      reason: values.reason || null,
    });
  });

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label>Policy</Label>
        <Select
          value={form.watch("policy_id")}
          onValueChange={(v) => form.setValue("policy_id", v)}
          disabled={balancesLoading}
        >
          <SelectTrigger>
            <SelectValue placeholder={balancesLoading ? "Loading policies..." : "Select a policy"} />
          </SelectTrigger>
          <SelectContent>
            {balances?.map((balance) => (
              <SelectItem key={balance.policy_id} value={balance.policy_id}>
                {balance.policy_key} ({balance.policy_category})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="start_at">Start</Label>
          <Input id="start_at" type="datetime-local" {...form.register("start_at", { required: true })} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="end_at">End</Label>
          <Input id="end_at" type="datetime-local" {...form.register("end_at", { required: true })} />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="reason">Reason (optional)</Label>
        <Textarea id="reason" placeholder="Why are you requesting time off?" {...form.register("reason")} />
      </div>

      <Button type="submit" className="w-full" disabled={isPending || !form.watch("policy_id")}>
        {isPending ? "Submitting..." : "Submit Request"}
      </Button>
    </form>
  );
}
