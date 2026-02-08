import { useQuery } from "@tanstack/react-query";
import { reportsApi } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/query-keys";
import { useAuth } from "@/lib/auth/use-auth";

export function useAuditLog(filters?: Record<string, unknown>) {
  const { companyId } = useAuth();
  return useQuery({
    queryKey: queryKeys.auditLog.all(companyId, filters),
    queryFn: () => reportsApi.auditLog(companyId, filters),
  });
}
