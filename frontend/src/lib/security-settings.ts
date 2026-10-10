/**
 * The user's own test-security switches, saved on their profile.
 *
 * Every switch defaults to on, which is how the tests behaved before the
 * switches existed. The keys and defaults mirror backend/accounts/security.py.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchJson } from '@/lib/backend';

export interface SecuritySettings {
  /** Speaking: switching tab or window asks whether to cancel the test. */
  leave_window_cancels_speaking: boolean;
  /** Reading/Listening: count leaving the window and show the count. */
  count_leaving_window: boolean;
  /** Reading: block copying the passage text. */
  block_copying: boolean;
  /** Any test: the browser asks before the page is closed or refreshed. */
  warn_before_leaving_page: boolean;
}

export const DEFAULT_SECURITY_SETTINGS: SecuritySettings = {
  leave_window_cancels_speaking: true,
  count_leaving_window: true,
  block_copying: true,
  warn_before_leaving_page: true,
};

const QUERY_KEY = ['security-settings'];
const URL = '/api/auth/security-settings';

async function fetchSecuritySettings(): Promise<SecuritySettings> {
  const data = await fetchJson<{ settings: Partial<SecuritySettings> }>(URL);
  return { ...DEFAULT_SECURITY_SETTINGS, ...data.settings };
}

/**
 * The current switches. Until they load, or if loading fails, the defaults
 * apply - so the protections stay on rather than silently dropping out.
 */
export function useSecuritySettings(): SecuritySettings {
  const { data } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchSecuritySettings,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
  return data ?? DEFAULT_SECURITY_SETTINGS;
}

/** Change one or more switches; the cache updates from the server's answer. */
export function useUpdateSecuritySettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (changes: Partial<SecuritySettings>) =>
      fetchJson<{ settings: SecuritySettings }>(URL, {
        method: 'PATCH',
        body: JSON.stringify({ settings: changes }),
      }).then((data) => ({ ...DEFAULT_SECURITY_SETTINGS, ...data.settings })),
    onSuccess: (settings) => queryClient.setQueryData(QUERY_KEY, settings),
  });
}
