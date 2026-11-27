import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

const html = await readFile(new URL('../index.html', import.meta.url), 'utf8');

test('the page links the uncached manifest route, not the immutable /assets copy', () => {
  // /assets is cached for a year, so phones never saw a new scope (the URL bar bug).
  assert.match(
    html,
    /<link rel="manifest" href="\/books\/manifest\.webmanifest" \/>/
  );
  assert.doesNotMatch(html, /\/assets\/[^"]*manifest/);
});

test('iOS names the home screen app RareBooks', () => {
  assert.match(
    html,
    /<meta name="apple-mobile-web-app-title" content="RareBooks" \/>/
  );
});
