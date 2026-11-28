import { listenForInstallPrompt, registerServiceWorker } from './pwa';
import { listenForPushClicks } from 'src/utils/pushNotifications';
import { useTranslations } from './translations';

async function start() {
  useTranslations(window.frappe?.boot?.__messages ?? {});
  // Load models and components after their static labels can be translated.
  await import('./mount');
}

// The app is also served at /books (the apps screen and older links), which the
// service worker's /books/ scope misses; land on /books/ so it controls the page.
if (location.pathname === '/books') {
  history.replaceState(
    history.state,
    '',
    `/books/${location.search}${location.hash}`
  );
}

listenForInstallPrompt();
registerServiceWorker();
// A tapped push moves an open /books tab to its link (spec 0026 AC-11).
listenForPushClicks();
void start();
