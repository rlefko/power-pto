import { type ReactNode, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { RequestForm } from "./request-form";
import { useSubmitRequest } from "../hooks/use-requests";
import type { TimeOffRequestCreate } from "@/lib/api/types";
import { toast } from "sonner";
import { extractErrorMessage } from "@/lib/api/client";

interface SubmitRequestDialogProps {
  trigger: ReactNode;
}

export function SubmitRequestDialog({ trigger }: SubmitRequestDialogProps) {
  const [open, setOpen] = useState(false);
  const submitRequest = useSubmitRequest();

  const handleSubmit = (data: TimeOffRequestCreate) => {
    submitRequest.mutate(data, {
      onSuccess: () => {
        toast.success("Time-off request submitted");
        setOpen(false);
      },
      onError: (err) => toast.error(extractErrorMessage(err)),
    });
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Request Time Off</DialogTitle>
        </DialogHeader>
        <RequestForm onSubmit={handleSubmit} isPending={submitRequest.isPending} />
      </DialogContent>
    </Dialog>
  );
}
