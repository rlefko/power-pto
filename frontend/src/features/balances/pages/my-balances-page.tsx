import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { CardGridSkeleton } from "@/components/shared/loading-skeleton";
import { EmptyState } from "@/components/shared/empty-state";
import { BalanceCard } from "../components/balance-card";
import { useEmployeeBalances } from "../hooks/use-balances";
import { useAuth } from "@/lib/auth/use-auth";
import { extractErrorMessage } from "@/lib/api/client";
import { toast } from "sonner";
import { CalendarPlus } from "lucide-react";

export function MyBalancesPage() {
  const { userId } = useAuth();
  const { data: balances, isLoading, isError, error } = useEmployeeBalances(userId);

  const handleRequestTimeOff = () => {
    toast.info("Request time off flow coming soon");
  };

  if (isError) {
    return (
      <div className="space-y-6">
        <PageHeader title="My Balances" />
        <div className="text-center text-destructive">{extractErrorMessage(error)}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Balances"
        subtitle="Your current time-off balances"
        actions={
          <Button size="sm" onClick={handleRequestTimeOff}>
            <CalendarPlus className="mr-1 h-4 w-4" />
            Request Time Off
          </Button>
        }
      />

      {isLoading ? (
        <CardGridSkeleton count={3} />
      ) : !balances || balances.length === 0 ? (
        <EmptyState title="No balances" description="You are not assigned to any time-off policies yet." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {balances.map((balance) => (
            <BalanceCard key={balance.policy_id} balance={balance} />
          ))}
        </div>
      )}
    </div>
  );
}
