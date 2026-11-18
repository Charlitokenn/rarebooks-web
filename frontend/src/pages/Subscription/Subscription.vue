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
        </section>
      </div>
    </FrappeScrollArea>
  </div>
</template>

<script setup lang="ts">
import { ScrollArea as FrappeScrollArea } from 'frappe-ui';
import { t } from 'fyo';
import PageHeader from 'src/components/PageHeader.vue';
import { subscriptionStatus } from 'src/utils/refs';
import {
  formatDate,
  getTrialDaysLeft,
  isManaged,
  refreshSubscriptionStatus,
} from 'src/utils/subscription';
import { computed, onActivated } from 'vue';

type Row = { label: string; value: string; testid: string };

const status = subscriptionStatus;
const unpaidTrial = computed(() =>
  ['trial', 'prompt', 'locked'].includes(status.value?.phase ?? '')
);

const heading = computed(() => {
  if (status.value?.locked) {
    return t`Read only`;
  }

  return unpaidTrial.value ? t`Free trial` : t`Subscribed`;
});

const rows = computed<Row[]>(() => {
  const current = status.value;
  if (!current) {
    return [];
  }

  if (!unpaidTrial.value) {
    return [
      {
        label: t`Paid until`,
        value: formatDate(current.paid_until),
        testid: 'paid-until',
      },
    ];
  }

  const rows: Row[] = [];
  if (current.phase !== 'locked') {
    rows.push({
      label: t`Days left in the trial`,
      value: String(getTrialDaysLeft(current)),
      testid: 'trial-days-left',
    });
  }

  rows.push(
    {
      label: t`Trial ends on`,
      value: formatDate(current.trial_ends_on),
      testid: 'trial-ends-on',
    },
    {
      label: t`Read only from`,
      value: formatDate(current.lock_starts_on),
      testid: 'lock-starts-on',
    }
  );
  return rows;
});

// The page is kept alive, so it fetches the status again each time it opens.
onActivated(() => {
  void refreshSubscriptionStatus().catch(() => undefined);
});
</script>
