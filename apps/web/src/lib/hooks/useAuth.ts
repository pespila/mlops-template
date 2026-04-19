import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api, type CurrentUser } from "@/lib/api/client";

const ME_KEY = ["auth", "me"] as const;

export function useCurrentUser() {
  return useQuery<CurrentUser | null, ApiError>({
    queryKey: ME_KEY,
    queryFn: async () => {
      try {
        return await api.auth.me();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return null;
        throw err;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function useLoginMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { email: string; password: string }) => api.auth.login(input),
    onSuccess: (user) => {
      qc.setQueryData(ME_KEY, user);
    },
  });
}

export function useLogoutMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.auth.logout(),
    onSuccess: () => {
      qc.setQueryData(ME_KEY, null);
      qc.clear();
    },
  });
}
