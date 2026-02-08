import { useState } from "react";
import { useForm } from "react-hook-form";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateHoliday } from "../hooks/use-holidays";
import { toast } from "sonner";
import { extractErrorMessage } from "@/lib/api/client";
import { Plus } from "lucide-react";

interface FormValues {
  date: string;
  name: string;
}

export function AddHolidayDialog() {
  const [open, setOpen] = useState(false);
  const createHoliday = useCreateHoliday();

  const form = useForm<FormValues>({
    defaultValues: {
      date: "",
      name: "",
    },
  });

  const handleSubmit = form.handleSubmit((values) => {
    createHoliday.mutate(
      { date: values.date, name: values.name },
      {
        onSuccess: () => {
          toast.success("Holiday added");
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
        <Button size="sm">
          <Plus className="mr-1 h-4 w-4" />
          Add Holiday
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Holiday</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="date">Date</Label>
            <Input id="date" type="date" {...form.register("date", { required: true })} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="name">Holiday Name</Label>
            <Input id="name" placeholder="e.g. New Year's Day" {...form.register("name", { required: true })} />
          </div>
          <Button type="submit" className="w-full" disabled={createHoliday.isPending}>
            {createHoliday.isPending ? "Adding..." : "Add Holiday"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
