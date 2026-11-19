import { t } from 'fyo';
import type { DropdownOptions } from 'frappe-ui';
import { call } from 'src/web/api';
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
  window.open(
    'https://docs.frappe.io/' + (docsPathRef.value || 'books'),
    '_blank',
    'noopener,noreferrer'
  );
}

async function logOut() {
  // The next user on this browser must not see this user's chat (spec 0009 AC-9).
  await endSupportChat();
  await call('logout');
  window.location.assign('/login');
}
