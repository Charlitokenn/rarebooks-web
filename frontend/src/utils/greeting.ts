import { t } from 'fyo';

type GreetingBoot = {
  user?: { name?: string; first_name?: string | null };
  user_info?: Record<string, { fullname?: string }>;
};

/**
 * The name the dashboard greets the signed in user by: their Frappe first
 * name, else their full name, else nothing (scope feature 24). Frappe's
 * `user_info` falls back to the user id when the user has no full name,
 * so that fallback counts as no name.
 */
export function getGreetingName(
  boot: GreetingBoot | undefined = window.frappe?.boot
): string {
  const user = boot?.user?.name ?? '';
  const firstName = boot?.user?.first_name?.trim();
  if (firstName) {
    return firstName;
  }

  const fullName = boot?.user_info?.[user]?.fullname?.trim() ?? '';
  return fullName === user ? '' : fullName;
}

/** Good morning before 12:00, Good afternoon until 17:00, Good evening after, by the device clock. */
export function getGreeting(now: Date, name: string): string {
  const hour = now.getHours();
  if (hour < 12) {
    return name ? t`Good morning, ${name}` : t`Good morning`;
  }
  if (hour < 17) {
    return name ? t`Good afternoon, ${name}` : t`Good afternoon`;
  }
  return name ? t`Good evening, ${name}` : t`Good evening`;
}
