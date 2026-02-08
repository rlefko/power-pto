import { useMutation, useQueryClient } from "@tanstack/react-query";
import { employeesApi, adjustmentsApi } from "@/lib/api/endpoints";
import type { EmployeeUpsert, AdjustmentCreate } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/use-auth";

export function useUpsertEmployee() {
  const { companyId } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ employeeId, data }: { employeeId: string; data: EmployeeUpsert }) =>
      employeesApi.upsert(companyId, employeeId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["employees", companyId] });
    },
  });
}

export function useCreateAdjustment() {
  const { companyId } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: AdjustmentCreate) => adjustmentsApi.create(companyId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["balances", companyId] });
      queryClient.invalidateQueries({ queryKey: ["ledger", companyId] });
    },
  });
}
