<template>
  <div class="flex flex-col overflow-y-hidden">
    <PageHeader :title="t`Subscription`" />
    <FrappeScrollArea class="min-h-0 flex-1" viewport-class="pb-10">
      <div class="mx-auto max-w-2xl space-y-4 px-3 pt-5 sm:px-5">
        <p
          v-if="!status || !isManaged(status)"
          class="text-p-base text-ink-gray-7"
        >
          {{ t`This site is not on a hosted plan.` }}
        </p>
        <section
          v-else
          class="rounded-6 border border-outline-gray-1 p-4 text-ink-gray-8"
        >
          <h2 class="text-lg-semibold">{{ heading }}</h2>
          <dl class="mt-4 space-y-3 text-base">
            <div
              v-for="row in rows"
              :key="row.label"
              class="flex flex-wrap justify-between gap-x-4 gap-y-1"
            >
              <dt class="text-ink-gray-6">{{ row.label }}</dt>
              <dd class="font-medium" :data-testid="row.testid">
                {{ row.value }}
              </dd>
            </div>
          </dl>
          <p
            v-if="startsNote"
            class="mt-4 text-base text-ink-gray-7"
            data-testid="subscription-starts-on"
          >
            {{ startsNote }}
          </p>
          <p
            v-if="status.payment_pending"
            class="mt-4 text-base text-ink-gray-7"
            data-testid="payment-pending"
          >
            {{
              t`Payment pending. The lock lifts as soon as your payment is confirmed.`
            }}
          </p>
        </section>
        <section
          v-if="showPlans"
          class="rounded-6 border border-outline-gray-1 p-4 text-ink-gray-8"
          data-testid="subscription-plans"
        >
          <h2 class="text-lg-semibold">{{ t`Plans` }}</h2>
          <div
            v-if="billingError"
            role="alert"
            class="mt-4 flex flex-wrap items-center justify-between gap-3 text-base"
          >
            <p class="text-ink-red-6">{{ billingError }}</p>
            <FrappeButton
              :label="t`Retry`"
              :loading="isRefreshing"
              @click="refresh(true)"
            />
          </div>
          <p
            v-else-if="!status?.offered_provider"
            class="mt-4 text-base text-ink-gray-7"
          >
            {{ t`Finish setup first.` }}
          </p>
          <ul v-else class="mt-4 space-y-3">
            <li
              v-for="plan in status?.plans ?? []"
              :key="plan.billing_period"
              class="flex flex-wrap items-center justify-between gap-3"
              :data-testid="`plan-${plan.billing_period}`"
            >
              <div class="min-w-0 text-base">
                <p class="font-medium">{{ getPlanLabel(plan) }}</p>
                <p class="text-ink-gray-6">{{ formatPlanPrice(plan) }}</p>
              </div>
              <FrappeButton
                variant="solid"
                :label="t`Subscribe`"
                :loading="checkoutPeriod === plan.billing_period"
                :disabled="!!checkoutPeriod"
                @click="subscribe(plan)"
              />
            </li>
          </ul>
          <p
            v-if="checkoutError"
            role="alert"
            class="mt-3 text-base text-ink-red-6"
          >
            {{ checkoutError }}
          </p>
        </section>
      </div>
    </FrappeScrollArea>
  </div>
</template>

<script setup lang="ts">
import {
  Button as FrappeButton,
  ScrollArea as FrappeScrollArea,
} from 'frappe-ui';
import { t } from 'fyo';
import PageHeader from 'src/components/PageHeader.vue';
import { subscriptionStatus } from 'src/utils/refs';
import {
  formatPlanPrice,
  getPlanLabel,
  getSubscriptionDetails,
  getSubscriptionStartsNote,
  isCheckoutReturn,
  isManaged,
  refreshSubscriptionStatus,
  startCheckout,
  type SubscriptionPlan,
} from 'src/utils/subscription';
import { computed, onActivated, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

const route = useRoute();
const router = useRouter();
const status = subscriptionStatus;
const isRefreshing = ref(false);
const loadError = ref<string | null>(null);
const checkoutPeriod = ref<SubscriptionPlan['billing_period'] | null>(null);
const checkoutError = ref<string | null>(null);

const startsNote = computed(() => getSubscriptionStartsNote(status.value));
// An active plan is changed with the provider, and a PayPal subscription waiting to start needs no
// second checkout, so neither offers plans (spec 0008 AC-21).
const showPlans = computed(
  () =>
    !!status.value &&
    isManaged(status.value) &&
    status.value.can_subscribe &&
    status.value.phase !== 'active' &&
    !startsNote.value
);
const billingError = computed(
  () => loadError.value ?? status.value?.plans_error ?? null
);
const details = computed(() =>
  status.value ? getSubscriptionDetails(status.value) : null
);
const heading = computed(() => details.value?.heading ?? '');
const rows = computed(() => details.value?.rows ?? []);

async function refresh(pull = false) {
  isRefreshing.value = true;
  try {
    await refreshSubscriptionStatus({ pull });
    loadError.value = null;
  } catch {
    loadError.value = t`Couldn't reach billing. Try again.`;
  } finally {
    isRefreshing.value = false;
  }
}

async function subscribe(plan: SubscriptionPlan) {
  checkoutPeriod.value = plan.billing_period;
  checkoutError.value = null;
  try {
    window.location.href = await startCheckout(plan.billing_period);
  } catch (error) {
    checkoutError.value = (error as Error).message;
    checkoutPeriod.value = null;
  }
}

// The page is kept alive, so it fetches the status again each time it opens. Back from checkout,
// the server pulls fresh state from billing, and the shared ref clears the banner without a reload (AC-12).
onActivated(() => {
  checkoutPeriod.value = null;
  const returned = isCheckoutReturn(route.query);
  if (returned) {
    void router.replace({ query: {} });
  }

  void refresh(returned);
});
</script>
