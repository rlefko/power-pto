import { useState } from "react";
import { useParams, useNavigate } from "react-router";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PageHeader } from "@/components/shared/page-header";
import { DetailSkeleton } from "@/components/shared/loading-skeleton";
import { EmptyState } from "@/components/shared/empty-state";
import { BalanceCard } from "@/features/balances/components/balance-card";
import { LedgerTable } from "@/features/balances/components/ledger-table";
import { AssignmentListByEmployee } from "../components/assignment-list-by-employee";
import { AdjustmentDialog } from "../components/adjustment-dialog";
import { EmployeeFormDialog } from "../components/employee-form";
import { useEmployee } from "../hooks/use-employees";
import { useEmployeeBalances } from "@/features/balances/hooks/use-balances";
import { useAuth } from "@/lib/auth/use-auth";
import { formatDate } from "@/lib/utils/format";
import { ArrowLeft, Pencil } from "lucide-react";

export function EmployeeDetailPage() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const navigate = useNavigate();
  const { role } = useAuth();
  const isAdmin = role === "admin";
  const { data: employee, isLoading } = useEmployee(employeeId!);
  const { data: balances, isLoading: balancesLoading } = useEmployeeBalances(employeeId!);
  const [selectedPolicyId, setSelectedPolicyId] = useState<string>("");

  if (isLoading) return <DetailSkeleton />;
  if (!employee) {
    return <div className="text-center text-muted-foreground">Employee not found</div>;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${employee.first_name} ${employee.last_name}`}
        subtitle={employee.email}
        actions={
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => navigate("/employees")}>
              <ArrowLeft className="mr-1 h-4 w-4" />
              Back
            </Button>
            {isAdmin && (
              <EmployeeFormDialog
                employee={employee}
                trigger={
                  <Button size="sm">
                    <Pencil className="mr-1 h-4 w-4" />
                    Edit
                  </Button>
                }
              />
            )}
          </div>
        }
      />

      <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
        <span>
          Pay type: <span className="font-medium text-foreground capitalize">{employee.pay_type.toLowerCase()}</span>
        </span>
        <span>
          Workday: <span className="font-medium text-foreground">{employee.workday_minutes / 60}h</span>
        </span>
        <span>
          Timezone: <span className="font-medium text-foreground">{employee.timezone}</span>
        </span>
        {employee.hire_date && (
          <span>
            Hired: <span className="font-medium text-foreground">{formatDate(employee.hire_date)}</span>
          </span>
        )}
      </div>

      <Tabs defaultValue="balances">
        <TabsList>
          <TabsTrigger value="balances">Balances</TabsTrigger>
          <TabsTrigger value="ledger">Ledger</TabsTrigger>
          <TabsTrigger value="assignments">Assignments</TabsTrigger>
        </TabsList>

        <TabsContent value="balances" className="mt-4">
          {balancesLoading ? (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-40 animate-pulse rounded-lg border bg-muted" />
              ))}
            </div>
          ) : !balances || balances.length === 0 ? (
            <EmptyState title="No balances" description="This employee has no policy assignments." />
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {balances.map((balance) => (
                <div key={balance.policy_id} className="space-y-2">
                  <BalanceCard balance={balance} />
                  {isAdmin && (
                    <AdjustmentDialog
                      employeeId={employeeId!}
                      policyId={balance.policy_id}
                      policyKey={balance.policy_key}
                    />
                  )}
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="ledger" className="mt-4">
          <div className="space-y-4">
            <Select value={selectedPolicyId} onValueChange={setSelectedPolicyId}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder="Select a policy" />
              </SelectTrigger>
              <SelectContent>
                {balances?.map((b) => (
                  <SelectItem key={b.policy_id} value={b.policy_id}>
                    {b.policy_key}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {selectedPolicyId ? (
              <LedgerTable employeeId={employeeId!} policyId={selectedPolicyId} />
            ) : (
              <p className="text-sm text-muted-foreground">Select a policy to view ledger entries.</p>
            )}
          </div>
        </TabsContent>

        <TabsContent value="assignments" className="mt-4">
          <AssignmentListByEmployee employeeId={employeeId!} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
