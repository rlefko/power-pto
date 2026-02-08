import { useState } from "react";
import { useForm } from "react-hook-form";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useCreateAdjustment } from "../hooks/use-employee-mutations";
import { toast } from "sonner";
import { extractErrorMessage } from "@/lib/api/client";
import { Plus } from "lucide-react";

interface AdjustmentDialogProps {
  employeeId: string;
  policyId: string;
  policyKey: string;
}

interface FormValues {
  amount_minutes: string;
  reason: string;
}

export function AdjustmentDialog({ employeeId, policyId, policyKey }: AdjustmentDialogProps) {
  const [open, setOpen] = useState(false);
  const createAdjustment = useCreateAdjustment();

  const form = useForm<FormValues>({
    defaultValues: {
      amount_minutes: "",
      reason: "",
    },
  });

  const handleSubmit = form.handleSubmit((values) => {
    createAdjustment.mutate(
      {
        employee_id: employeeId,
        policy_id: policyId,
        amount_minutes: parseInt(values.amount_minutes, 10),
        reason: values.reason,
      },
      {
        onSuccess: () => {
          toast.success("Adjustment created");
          form.reset();
          setOpen(false);
        },
        onError: (err) => toast.error(extractErrorMessage(err)),
      },
    );
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="w-full">
          <Plus className="mr-1 h-3 w-3" />
          Adjust
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Adjust Balance — {policyKey}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="amount_minutes">Amount (minutes)</Label>
            <Input
              id="amount_minutes"
              type="number"
              placeholder="Positive to add, negative to subtract"
              {...form.register("amount_minutes", { required: true })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="reason">Reason</Label>
            <Textarea
              id="reason"
              placeholder="Reason for this adjustment"
              {...form.register("reason", { required: true })}
            />
          </div>
          <Button type="submit" className="w-full" disabled={createAdjustment.isPending}>
            {createAdjustment.isPending ? "Creating..." : "Create Adjustment"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
