import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { CardGridSkeleton } from "@/components/shared/loading-skeleton";
import { EmptyState } from "@/components/shared/empty-state";
import { PolicyCard } from "../components/policy-card";
import { PolicyForm } from "../components/policy-form";
import { usePolicies, useCreatePolicy } from "../hooks/use-policies";
import { useAuth } from "@/lib/auth/use-auth";
import type { PolicyCreate, PolicyUpdate } from "@/lib/api/types";
import { toast } from "sonner";
import { extractErrorMessage } from "@/lib/api/client";
import { Plus } from "lucide-react";

export function PoliciesPage() {
  const { role } = useAuth();
  const isAdmin = role === "admin";
  const { data, isLoading, isError, error } = usePolicies();
  const createPolicy = useCreatePolicy();
  const [dialogOpen, setDialogOpen] = useState(false);

  const handleCreate = (formData: PolicyCreate | PolicyUpdate) => {
    createPolicy.mutate(formData as PolicyCreate, {
      onSuccess: () => {
        toast.success("Policy created");
        setDialogOpen(false);
      },
      onError: (err) => toast.error(extractErrorMessage(err)),
    });
  };

  if (isError) {
    return (
      <div className="space-y-6">
        <PageHeader title="Policies" />
        <div className="text-center text-destructive">{extractErrorMessage(error)}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Policies"
        subtitle="Manage time-off policies"
        actions={
          isAdmin ? (
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button size="sm">
                  <Plus className="mr-1 h-4 w-4" />
                  Create Policy
                </Button>
              </DialogTrigger>
              <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
                <DialogHeader>
                  <DialogTitle>Create Policy</DialogTitle>
                </DialogHeader>
                <PolicyForm mode="create" onSubmit={handleCreate} isPending={createPolicy.isPending} />
              </DialogContent>
            </Dialog>
          ) : undefined
        }
      />

      {isLoading ? (
        <CardGridSkeleton count={6} />
      ) : data?.items.length === 0 ? (
        <EmptyState
          title="No policies yet"
          description="Create a time-off policy to get started."
          actionLabel={isAdmin ? "Create Policy" : undefined}
          onAction={isAdmin ? () => setDialogOpen(true) : undefined}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {data?.items.map((policy) => (
            <PolicyCard key={policy.id} policy={policy} />
          ))}
        </div>
      )}
    </div>
  );
}
