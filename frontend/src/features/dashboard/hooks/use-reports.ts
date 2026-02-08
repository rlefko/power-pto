import { useQuery } from "@tanstack/react-query";
import { reportsApi } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/query-keys";
import { useAuth } from "@/lib/auth/use-auth";

export function useBalanceSummary() {
  const { companyId } = useAuth();
  return useQuery({
    queryKey: queryKeys.reports.balances(companyId),
    queryFn: () => reportsApi.balanceSummary(companyId),
  });
}
