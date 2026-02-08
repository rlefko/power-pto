import { useState } from "react";
import { useForm } from "react-hook-form";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { AssignmentCreate } from "@/lib/api/types";
import { useCreateAssignment } from "../hooks/use-assignments";
import { toast } from "sonner";
import { extractErrorMessage } from "@/lib/api/client";
import { Plus } from "lucide-react";

interface AssignEmployeeDialogProps {
  policyId: string;
}

interface FormValues {
  employee_id: string;
  effective_from: string;
  effective_to: string;
}

export function AssignEmployeeDialog({ policyId }: AssignEmployeeDialogProps) {
  const [open, setOpen] = useState(false);
  const createAssignment = useCreateAssignment(policyId);

  const form = useForm<FormValues>({
    defaultValues: {
      employee_id: "",
      effective_from: new Date().toISOString().split("T")[0],
      effective_to: "",
    },
  });

  const handleSubmit = form.handleSubmit((values) => {
    const data: AssignmentCreate = {
      employee_id: values.employee_id,
      effective_from: values.effective_from,
      effective_to: values.effective_to || null,
    };

    createAssignment.mutate(data, {
      onSuccess: () => {
        toast.success("Employee assigned");
        form.reset();
        setOpen(false);
      },
      onError: (err) => toast.error(extractErrorMessage(err)),
    });
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="mr-1 h-4 w-4" />
          Assign Employee
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Assign Employee</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="employee_id">Employee ID</Label>
            <Input
              id="employee_id"
              placeholder="UUID of the employee"
              {...form.register("employee_id", { required: true })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="effective_from">Effective From</Label>
            <Input id="effective_from" type="date" {...form.register("effective_from", { required: true })} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="effective_to">Effective To (optional)</Label>
            <Input id="effective_to" type="date" {...form.register("effective_to")} />
          </div>
          <Button type="submit" className="w-full" disabled={createAssignment.isPending}>
            {createAssignment.isPending ? "Assigning..." : "Assign"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
