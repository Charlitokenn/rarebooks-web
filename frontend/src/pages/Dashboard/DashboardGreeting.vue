<template>
  <!-- Wraps a long name instead of overflowing a phone. -->
  <h2
    class="break-words text-2xl-semibold text-ink-gray-8 md:text-3xl-semibold"
  >
    {{ greeting }}
  </h2>
</template>

<script setup lang="ts">
import { getGreeting, getGreetingName } from 'src/utils/greeting';
import { computed, onActivated, onDeactivated, onMounted, ref } from 'vue';

// The user's own device clock picks the time of day (scope feature 24).
const now = ref(new Date());
const name = getGreetingName();
const greeting = computed(() => getGreeting(now.value, name));

// The dashboard stays alive between visits, so check the clock on each
// visit and each minute while it shows.
let timer: ReturnType<typeof setInterval> | undefined;
function startClock() {
  now.value = new Date();
  clearInterval(timer);
  timer = setInterval(() => (now.value = new Date()), 60_000);
}
function stopClock() {
  clearInterval(timer);
  timer = undefined;
}

onMounted(startClock);
onActivated(startClock);
onDeactivated(stopClock);
</script>
