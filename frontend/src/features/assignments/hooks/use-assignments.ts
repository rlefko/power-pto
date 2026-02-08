import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { assignmentsApi } from "@/lib/api/endpoints";
import type { AssignmentCreate } from "@/lib/api/types";
import { queryKeys } from "@/lib/query-keys";
import { useAuth } from "@/lib/auth/use-auth";

export function useAssignmentsByPolicy(policyId: string) {
  const { companyId } = useAuth();
  return useQuery({
    queryKey: queryKeys.assignments.byPolicy(companyId, policyId),
    queryFn: () => assignmentsApi.listByPolicy(companyId, policyId),
  });
}

export function useAssignmentsByEmployee(employeeId: string) {
  const { companyId } = useAuth();
  return useQuery({
    queryKey: queryKeys.assignments.byEmployee(companyId, employeeId),
    queryFn: () => assignmentsApi.listByEmployee(companyId, employeeId),
  });
}

export function useCreateAssignment(policyId: string) {
  const { companyId } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: AssignmentCreate) => assignmentsApi.createForPolicy(companyId, policyId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.assignments.byPolicy(companyId, policyId),
      });
    },
  });
}

export function useEndDateAssignment() {
  const { companyId } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ assignmentId, effectiveTo }: { assignmentId: string; effectiveTo?: string }) =>
      assignmentsApi.endDate(companyId, assignmentId, effectiveTo),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["assignments", companyId],
      });
    },
  });
}
