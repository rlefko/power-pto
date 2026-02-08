import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { requestsApi, balancesApi } from "@/lib/api/endpoints";
import type { TimeOffRequestCreate } from "@/lib/api/types";
import { queryKeys } from "@/lib/query-keys";
import { useAuth } from "@/lib/auth/use-auth";

export function useRequests(filters?: Record<string, string>) {
  const { companyId } = useAuth();
  return useQuery({
    queryKey: queryKeys.requests.all(companyId, filters),
    queryFn: () => requestsApi.list(companyId, filters),
  });
}

export function useEmployeeBalances(employeeId: string) {
  const { companyId } = useAuth();
  return useQuery({
    queryKey: queryKeys.balances.byEmployee(companyId, employeeId),
    queryFn: () => balancesApi.getByEmployee(companyId, employeeId),
    enabled: !!employeeId,
  });
}

export function useSubmitRequest() {
  const { companyId } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: TimeOffRequestCreate) => requestsApi.submit(companyId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["requests", companyId] });
      queryClient.invalidateQueries({ queryKey: ["balances", companyId] });
    },
  });
}

export function useApproveRequest() {
  const { companyId } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ requestId, note }: { requestId: string; note?: string }) =>
      requestsApi.approve(companyId, requestId, note ? { note } : undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["requests", companyId] });
      queryClient.invalidateQueries({ queryKey: ["balances", companyId] });
    },
  });
}

export function useDenyRequest() {
  const { companyId } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ requestId, note }: { requestId: string; note?: string }) =>
      requestsApi.deny(companyId, requestId, note ? { note } : undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["requests", companyId] });
      queryClient.invalidateQueries({ queryKey: ["balances", companyId] });
    },
  });
}

export function useCancelRequest() {
  const { companyId } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (requestId: string) => requestsApi.cancel(companyId, requestId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["requests", companyId] });
      queryClient.invalidateQueries({ queryKey: ["balances", companyId] });
    },
  });
}
