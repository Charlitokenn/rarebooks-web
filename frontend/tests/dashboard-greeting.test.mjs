import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  greeting,
  setLanguageMapOnTranslationString,
} from './helpers/frappe.mjs';

const { getGreeting, getGreetingName } = greeting;

/** A local time today on the device clock. */
function at(hours, minutes = 0) {
  const date = new Date(2031, 8, 15);
  date.setHours(hours, minutes, 0, 0);
  return date;
}

test('the greeting follows the time of day on the device clock', () => {
  const cases = [
    [at(0), 'Good morning, Asha'],
    [at(11, 59), 'Good morning, Asha'],
    [at(12), 'Good afternoon, Asha'],
    [at(16, 59), 'Good afternoon, Asha'],
    [at(17), 'Good evening, Asha'],
    [at(23, 59), 'Good evening, Asha'],
  ];
  for (const [now, expected] of cases) {
    assert.equal(getGreeting(now, 'Asha'), expected, now.toTimeString());
  }
});

test('without a name the greeting stands alone', () => {
  assert.equal(getGreeting(at(9), ''), 'Good morning');
  assert.equal(getGreeting(at(13), ''), 'Good afternoon');
  assert.equal(getGreeting(at(20), ''), 'Good evening');
});

test('the name is the first name, else the full name, else nothing', () => {
  const boot = (user, fullname) => ({
    user: { name: 'asha@shop.tz', ...user },
    user_info: { 'asha@shop.tz': { fullname } },
  });

  assert.equal(
    getGreetingName(boot({ first_name: ' Asha ' }, 'Asha Mushi')),
    'Asha'
  );
  assert.equal(
    getGreetingName(boot({ first_name: '' }, 'Asha Mushi')),
    'Asha Mushi'
  );
  assert.equal(getGreetingName(boot({ first_name: null }, '  ')), '');
  // Frappe fills fullname with the user id when the user has no name.
  assert.equal(getGreetingName(boot({}, 'asha@shop.tz')), '');
  assert.equal(getGreetingName(undefined), '');
});

test('each user sees their own name from their own session boot', () => {
  const ownBoot = (name, first_name) => ({ user: { name, first_name } });
  assert.equal(getGreetingName(ownBoot('asha@shop.tz', 'Asha')), 'Asha');
  assert.equal(getGreetingName(ownBoot('juma@shop.tz', 'Juma')), 'Juma');
});

test('the greeting is translated, with the name in its place', () => {
  setLanguageMapOnTranslationString({
    'Good morning, ${0}': { translation: 'Habari za asubuhi, ${0}' },
    'Good evening': { translation: 'Habari za jioni' },
  });
  try {
    assert.equal(getGreeting(at(8), 'Asha'), 'Habari za asubuhi, Asha');
    assert.equal(getGreeting(at(19), ''), 'Habari za jioni');
  } finally {
    setLanguageMapOnTranslationString(undefined);
  }
});
