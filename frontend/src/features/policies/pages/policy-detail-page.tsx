import { useState } from "react";
import { useParams, useNavigate } from "react-router";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader } from "@/components/shared/page-header";
import { CategoryBadge } from "@/components/shared/category-badge";
import { DetailSkeleton } from "@/components/shared/loading-skeleton";
import { PolicySettingsDisplay } from "../components/policy-settings-display";
import { PolicyVersionList } from "../components/policy-version-list";
import { PolicyForm } from "../components/policy-form";
import { AssignmentList } from "@/features/assignments/components/assignment-list";
import { AssignEmployeeDialog } from "@/features/assignments/components/assign-employee-dialog";
import { usePolicy, usePolicyVersions, useUpdatePolicy } from "../hooks/use-policies";
import { useAuth } from "@/lib/auth/use-auth";
import type { PolicyCreate, PolicyUpdate } from "@/lib/api/types";
import { toast } from "sonner";
import { extractErrorMessage } from "@/lib/api/client";
import { ArrowLeft, Pencil } from "lucide-react";

export function PolicyDetailPage() {
  const { policyId } = useParams<{ policyId: string }>();
  const navigate = useNavigate();
  const { role } = useAuth();
  const isAdmin = role === "admin";
  const { data: policy, isLoading } = usePolicy(policyId!);
  const { data: versions, isLoading: versionsLoading } = usePolicyVersions(policyId!);
  const updatePolicy = useUpdatePolicy(policyId!);
  const [editOpen, setEditOpen] = useState(false);

  const handleUpdate = (formData: PolicyCreate | PolicyUpdate) => {
    updatePolicy.mutate(formData as PolicyUpdate, {
      onSuccess: () => {
        toast.success("Policy updated");
        setEditOpen(false);
      },
      onError: (err) => toast.error(extractErrorMessage(err)),
    });
  };

  if (isLoading) return <DetailSkeleton />;
  if (!policy) {
    return <div className="text-center text-muted-foreground">Policy not found</div>;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={policy.key}
        actions={
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => navigate("/policies")}>
              <ArrowLeft className="mr-1 h-4 w-4" />
              Back
            </Button>
            {isAdmin && (
              <Dialog open={editOpen} onOpenChange={setEditOpen}>
                <DialogTrigger asChild>
                  <Button size="sm">
                    <Pencil className="mr-1 h-4 w-4" />
                    Edit Policy
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
                  <DialogHeader>
                    <DialogTitle>Update Policy</DialogTitle>
                  </DialogHeader>
                  <PolicyForm mode="edit" onSubmit={handleUpdate} isPending={updatePolicy.isPending} />
                </DialogContent>
              </Dialog>
            )}
          </div>
        }
      />

      <div className="flex items-center gap-2">
        <CategoryBadge category={policy.category} />
      </div>

      <Tabs defaultValue="settings">
        <TabsList>
          <TabsTrigger value="settings">Settings</TabsTrigger>
          <TabsTrigger value="versions">Versions</TabsTrigger>
          <TabsTrigger value="assignments">Assignments</TabsTrigger>
        </TabsList>
        <TabsContent value="settings" className="mt-4">
          {policy.current_version ? (
            <PolicySettingsDisplay settings={policy.current_version.settings} />
          ) : (
            <p className="text-muted-foreground">No active version</p>
          )}
        </TabsContent>
        <TabsContent value="versions" className="mt-4">
          <PolicyVersionList
            versions={versions?.items ?? []}
            total={versions?.total ?? 0}
            isLoading={versionsLoading}
          />
        </TabsContent>
        <TabsContent value="assignments" className="mt-4">
          <div className="space-y-4">
            {isAdmin && <AssignEmployeeDialog policyId={policyId!} />}
            <AssignmentList policyId={policyId!} />
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
