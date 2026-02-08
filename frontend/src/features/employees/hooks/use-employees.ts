import { useQuery } from "@tanstack/react-query";
import { employeesApi } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/query-keys";
import { useAuth } from "@/lib/auth/use-auth";

export function useEmployees() {
  const { companyId } = useAuth();
  return useQuery({
    queryKey: queryKeys.employees.all(companyId),
    queryFn: () => employeesApi.list(companyId),
  });
}

export function useEmployee(employeeId: string) {
  const { companyId } = useAuth();
  return useQuery({
    queryKey: queryKeys.employees.detail(companyId, employeeId),
    queryFn: () => employeesApi.get(companyId, employeeId),
    enabled: !!employeeId,
  });
}
