<template>
  <div
    v-if="banner"
    role="status"
    data-testid="subscription-banner"
    class="flex flex-wrap items-center gap-x-3 gap-y-2 border-b px-4 py-2 text-base"
    :class="
      isLocked
        ? 'border-outline-red-1 bg-surface-red-2 text-ink-red-7'
        : 'border-outline-gray-1 bg-surface-amber-2 text-ink-amber-7'
    "
  >
    <span
      :class="isLocked ? 'lucide-lock' : 'lucide-calendar-clock'"
      class="size-4 shrink-0"
      aria-hidden="true"
    />
    <p class="min-w-0 flex-1">{{ banner.message }}</p>
    <FrappeButton
      v-if="banner.canSubscribe"
      variant="solid"
      :label="t`Subscribe`"
      @click="router.push(SUBSCRIPTION_ROUTE)"
    />
    <p v-else class="text-ink-gray-7">
      {{ t`Ask your administrator to subscribe.` }}
    </p>
    <FrappeButton
      v-if="isLocked && canChat"
      icon-left="lucide-message-circle"
      :label="t`Chat with support`"
      data-testid="banner-support-chat"
      @click="openSupportChat"
    />
    <FrappeButton
      v-if="banner.dismissible"
      variant="ghost"
      icon="lucide-x"
      :aria-label="t`Dismiss`"
      @click="dismiss"
    />
  </div>
</template>

<script setup lang="ts">
import { Button as FrappeButton } from 'frappe-ui';
import { subscriptionStatus } from 'src/utils/refs';
import {
  SUBSCRIPTION_ROUTE,
  dismissBanner,
  getDismissedOn,
  getSubscriptionBanner,
} from 'src/utils/subscription';
import { hasSupportChat, openSupportChat } from 'src/utils/supportChat';
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

const router = useRouter();
// Set once at startup from the boot, so it needs no reactivity.
const canChat = hasSupportChat();
const dismissedOn = ref(getDismissedOn());
const banner = computed(() =>
  getSubscriptionBanner(subscriptionStatus.value, dismissedOn.value)
);
const isLocked = computed(() => !!subscriptionStatus.value?.locked);

function dismiss() {
  const today = subscriptionStatus.value?.today;
  if (today) {
    dismissBanner(today);
    dismissedOn.value = today;
  }
}
</script>
