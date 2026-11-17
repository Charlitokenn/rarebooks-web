import type { ToastType } from 'src/utils/types';

/** A `frappe.msgprint` entry, as `/api/v2` sends it in `messages`. */
export interface ServerMessage {
  message: string;
  /** Not shown: a toast shows one line. */
  title?: string;
  /** Frappe's colour: orange, yellow, red, green, blue, ... */
  indicator?: string;
  /** Ignored: every message is a toast. */
  alert?: boolean | number;
}

const toastTypeByIndicator: Record<string, ToastType | undefined> = {
  orange: 'warning',
  yellow: 'warning',
  red: 'error',
  green: 'success',
};

/**
 * Shows each distinct message from a successful response as a toast.
 * Only the request layers call this; screens never handle server messages.
 * It never rejects: the request already succeeded, so a toast that fails to
 * show is logged, not reported as a failed request.
 */
export async function showServerMessages(
  messages: ServerMessage[] = []
): Promise<void> {
  try {
    await showToasts(getDistinctMessages(messages));
  } catch (error) {
    console.error('Could not show the server messages', messages, error);
  }
}

async function showToasts(distinct: ServerMessage[]): Promise<void> {
  if (!distinct.length) {
    return;
  }

  // Loaded on demand, as `showPreviewError` does, so the request layer doesn't pull in Vue.
  const { showToast } = await import('src/utils/interactive');
  for (const { message, indicator } of distinct) {
    const type = toastTypeByIndicator[indicator ?? ''] ?? 'info';
    const stays = type === 'warning' || type === 'error';
    showToast({
      // A repeat on a later request replaces the shown toast.
      id: `server-message:${message}`,
      // Already translated by the server; frappe-ui's toast sanitizes it.
      message,
      type,
      duration: stays ? 'until_closed' : 'long',
    });
  }
}

/** frappe-ui's `_server_messages`: JSON strings, or a plain string that fails to parse. */
export function parseServerMessages(raw: string[] = []): ServerMessage[] {
  return raw.map((entry) => {
    try {
      const value: unknown = JSON.parse(entry);
      return typeof value === 'string'
        ? { message: value }
        : (value as ServerMessage);
    } catch {
      return { message: entry };
    }
  });
}

/** One entry per text, keeping the first entry's indicator. */
function getDistinctMessages(messages: ServerMessage[]): ServerMessage[] {
  const byText = new Map<string, ServerMessage>();
  for (const entry of messages) {
    const message =
      typeof entry?.message === 'string' ? entry.message.trim() : '';
    if (message && !byText.has(message)) {
      byText.set(message, { message, indicator: entry.indicator });
    }
  }

  return [...byText.values()];
}
