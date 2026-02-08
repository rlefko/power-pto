import { useQuery } from "@tanstack/react-query";
import { balancesApi } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/query-keys";
import { useAuth } from "@/lib/auth/use-auth";

export function useEmployeeBalances(employeeId: string) {
  const { companyId } = useAuth();
  return useQuery({
    queryKey: queryKeys.balances.byEmployee(companyId, employeeId),
    queryFn: () => balancesApi.getByEmployee(companyId, employeeId),
  });
}

export function useEmployeeLedger(employeeId: string, policyId: string) {
  const { companyId } = useAuth();
  return useQuery({
    queryKey: queryKeys.ledger.byEmployeePolicy(companyId, employeeId, policyId),
    queryFn: () => balancesApi.getLedger(companyId, employeeId, policyId),
  });
}
