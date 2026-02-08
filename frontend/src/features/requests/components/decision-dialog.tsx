import { type ReactNode, useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useApproveRequest, useDenyRequest } from "../hooks/use-requests";
import { toast } from "sonner";
import { extractErrorMessage } from "@/lib/api/client";

interface DecisionDialogProps {
  requestId: string;
  variant: "approve" | "deny";
  trigger: ReactNode;
}

export function DecisionDialog({ requestId, variant, trigger }: DecisionDialogProps) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const approveRequest = useApproveRequest();
  const denyRequest = useDenyRequest();

  const mutation = variant === "approve" ? approveRequest : denyRequest;
  const title = variant === "approve" ? "Approve Request" : "Deny Request";

  const handleConfirm = () => {
    mutation.mutate(
      { requestId, note: note || undefined },
      {
        onSuccess: () => {
          toast.success(variant === "approve" ? "Request approved" : "Request denied");
          setNote("");
          setOpen(false);
        },
        onError: (err) => toast.error(extractErrorMessage(err)),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="decision-note">Note (optional)</Label>
          <Textarea
            id="decision-note"
            placeholder="Add a note..."
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            variant={variant === "deny" ? "destructive" : "default"}
            onClick={handleConfirm}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "..." : title}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
