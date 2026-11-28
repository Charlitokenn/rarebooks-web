import { t } from 'fyo';
import type { DropdownOptions } from 'frappe-ui';
import { call } from 'src/web/api';
import { openDocs } from './docs';
import {
  getPushState,
  stopPushForSignOut,
  turnOffPush,
  turnOnPush,
} from './pushNotifications';
import { docsPathRef } from './refs';
import { endSupportChat, hasSupportChat, openSupportChat } from './supportChat';
import { deskTheme, setDeskTheme, type DeskTheme } from './theme';

/** Phones have no keyboard shortcuts, so they pass no `openShortcuts`. */
export function getAppMenuItems(openShortcuts?: () => void): DropdownOptions {
  const shortcuts = openShortcuts
    ? [
        {
          label: t`Keyboard shortcuts`,
          icon: 'lucide-command',
          onClick: openShortcuts,
        },
      ]
    : [];
  const supportChat = hasSupportChat()
    ? [
        {
          label: t`Chat with support`,
          icon: 'lucide-message-circle',
          onClick: () => void openSupportChat(),
        },
      ]
    : [];
  const notifications = getNotificationItems();

  return [
    {
      group: t`Help`,
      hideLabel: true,
      options: [
        {
          label: t`Documentation`,
          icon: 'lucide-circle-help',
          onClick: openDocumentation,
        },
        ...supportChat,
        ...notifications,
        ...shortcuts,
      ],
    },
    {
      group: t`Account`,
      hideLabel: true,
      options: [
        {
          label: t`Theme`,
          icon: 'lucide-sun-moon',
          submenu: getThemeItems(),
        },
        {
          label: t`Apps`,
          icon: 'lucide-layout-grid',
          onClick: () => window.location.assign('/apps'),
        },
        { label: t`Log out`, icon: 'lucide-log-out', onClick: logOut },
      ],
    },
  ];
}

type MenuEntry = { label: string; icon: string; onClick: () => void };

/** Push notifications for this device, beside the support chat (spec 0026 AC-2, AC-4). */
function getNotificationItems(): MenuEntry[] {
  const state = getPushState();
  if (state === 'hidden') {
    return [];
  }

  if (state === 'on') {
    return [
      {
        label: t`Turn off notifications`,
        icon: 'lucide-bell-off',
        onClick: () => void turnOffPush(),
      },
    ];
  }

  return [
    {
      label: t`Turn on notifications`,
      icon: 'lucide-bell',
      onClick: () => void turnOnPush(),
    },
  ];
}

function getThemeItems(): DropdownOptions {
  const themes: [DeskTheme, string][] = [
    ['Light', t`Light`],
    ['Dark', t`Dark`],
    ['Automatic', t`Automatic`],
  ];
  return themes.map(([theme, label]) => ({
    label,
    selected: deskTheme.value === theme,
    onClick: () => setDeskTheme(theme),
  }));
}

export function openDocumentation() {
  openDocs(docsPathRef.value);
}

async function logOut() {
  // The next user on this browser must not get this user's notifications (spec 0026 AC-4).
  await stopPushForSignOut();
  // The next user on this browser must not see this user's chat (spec 0009 AC-9).
  await endSupportChat();
  await call('logout');
  window.location.assign('/login');
}
