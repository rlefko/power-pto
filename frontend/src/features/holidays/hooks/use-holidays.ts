import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { holidaysApi } from "@/lib/api/endpoints";
import type { HolidayCreate } from "@/lib/api/types";
import { queryKeys } from "@/lib/query-keys";
import { useAuth } from "@/lib/auth/use-auth";

export function useHolidays(year?: number) {
  const { companyId } = useAuth();
  return useQuery({
    queryKey: queryKeys.holidays.all(companyId, year),
    queryFn: () => holidaysApi.list(companyId, year ? { year } : undefined),
  });
}

export function useCreateHoliday() {
  const { companyId } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: HolidayCreate) => holidaysApi.create(companyId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["holidays", companyId] });
    },
  });
}

export function useDeleteHoliday() {
  const { companyId } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (holidayId: string) => holidaysApi.delete(companyId, holidayId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["holidays", companyId] });
    },
  });
}
