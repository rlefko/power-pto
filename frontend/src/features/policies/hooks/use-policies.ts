import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { policiesApi } from "@/lib/api/endpoints";
import type { PolicyCreate, PolicyUpdate } from "@/lib/api/types";
import { queryKeys } from "@/lib/query-keys";
import { useAuth } from "@/lib/auth/use-auth";

export function usePolicies() {
  const { companyId } = useAuth();
  return useQuery({
    queryKey: queryKeys.policies.all(companyId),
    queryFn: () => policiesApi.list(companyId),
  });
}

export function usePolicy(policyId: string) {
  const { companyId } = useAuth();
  return useQuery({
    queryKey: queryKeys.policies.detail(companyId, policyId),
    queryFn: () => policiesApi.get(companyId, policyId),
  });
}

export function usePolicyVersions(policyId: string) {
  const { companyId } = useAuth();
  return useQuery({
    queryKey: queryKeys.policies.versions(companyId, policyId),
    queryFn: () => policiesApi.listVersions(companyId, policyId),
  });
}

export function useCreatePolicy() {
  const { companyId } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PolicyCreate) => policiesApi.create(companyId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.policies.all(companyId) });
    },
  });
}

export function useUpdatePolicy(policyId: string) {
  const { companyId } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PolicyUpdate) => policiesApi.update(companyId, policyId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.policies.all(companyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.policies.detail(companyId, policyId) });
    },
  });
}
