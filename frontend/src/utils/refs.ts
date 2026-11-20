import { ModelNameEnum } from 'models/types';
import type { SubscriptionStatus } from 'src/utils/subscription';
import { reactive, ref } from 'vue';
import type { HistoryState } from 'vue-router';

export const showSidebar = ref(true);
export const docsPathRef = ref<string>('');
// `globalThis.history`, since the API layer imports these refs and node tests have no history.
const initialState = globalThis.history?.state as HistoryState | undefined;
export const historyState = reactive({
  forward: !!initialState?.forward,
  back: !!initialState?.back,
});

/** Desktop settings show in a dialog over the page; phones open a page. */
export const settingsDialog = reactive({
  open: false,
  tab: ModelNameEnum.AccountingSettings as string,
});

/** The site's trial clock and lock state, seeded from boot; the banner and Subscription page read it (spec 0005). */
export const subscriptionStatus = ref<SubscriptionStatus | null>(null);
