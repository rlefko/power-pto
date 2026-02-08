import { type ReactNode, useState } from "react";
import { useForm } from "react-hook-form";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { Employee, EmployeeUpsert } from "@/lib/api/types";
import { useUpsertEmployee } from "../hooks/use-employee-mutations";
import { toast } from "sonner";
import { extractErrorMessage } from "@/lib/api/client";

interface EmployeeFormDialogProps {
  employee?: Employee;
  trigger: ReactNode;
}

interface FormValues {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  pay_type: string;
  workday_minutes: string;
  timezone: string;
  hire_date: string;
}

export function EmployeeFormDialog({ employee, trigger }: EmployeeFormDialogProps) {
  const [open, setOpen] = useState(false);
  const upsertEmployee = useUpsertEmployee();
  const isEdit = !!employee;

  const form = useForm<FormValues>({
    defaultValues: {
      id: employee?.id ?? "",
      first_name: employee?.first_name ?? "",
      last_name: employee?.last_name ?? "",
      email: employee?.email ?? "",
      pay_type: employee?.pay_type ?? "SALARY",
      workday_minutes: String(employee?.workday_minutes ?? 480),
      timezone: employee?.timezone ?? "America/New_York",
      hire_date: employee?.hire_date ?? "",
    },
  });

  const handleSubmit = form.handleSubmit((values) => {
    const data: EmployeeUpsert = {
      first_name: values.first_name,
      last_name: values.last_name,
      email: values.email,
      pay_type: values.pay_type,
      workday_minutes: parseInt(values.workday_minutes, 10),
      timezone: values.timezone,
      hire_date: values.hire_date || null,
    };

    const employeeId = isEdit ? employee.id : values.id;

    upsertEmployee.mutate(
      { employeeId, data },
      {
        onSuccess: () => {
          toast.success(isEdit ? "Employee updated" : "Employee created");
          form.reset();
          setOpen(false);
        },
        onError: (err) => toast.error(extractErrorMessage(err)),
      },
    );
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Employee" : "Add Employee"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          {!isEdit && (
            <div className="space-y-2">
              <Label htmlFor="id">Employee ID</Label>
              <Input id="id" placeholder="UUID" {...form.register("id", { required: true })} />
            </div>
          )}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="first_name">First Name</Label>
              <Input id="first_name" {...form.register("first_name", { required: true })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="last_name">Last Name</Label>
              <Input id="last_name" {...form.register("last_name", { required: true })} />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" {...form.register("email", { required: true })} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Pay Type</Label>
              <Select value={form.watch("pay_type")} onValueChange={(v) => form.setValue("pay_type", v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="SALARY">Salary</SelectItem>
                  <SelectItem value="HOURLY">Hourly</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="workday_minutes">Workday (minutes)</Label>
              <Input
                id="workday_minutes"
                type="number"
                {...form.register("workday_minutes", { required: true, min: 1 })}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="timezone">Timezone</Label>
              <Input id="timezone" {...form.register("timezone", { required: true })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="hire_date">Hire Date</Label>
              <Input id="hire_date" type="date" {...form.register("hire_date")} />
            </div>
          </div>
          <Button type="submit" className="w-full" disabled={upsertEmployee.isPending}>
            {upsertEmployee.isPending ? "Saving..." : isEdit ? "Update Employee" : "Create Employee"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
