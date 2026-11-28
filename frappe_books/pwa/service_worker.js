// The server stamps the build hash and inlines the icon, so each build installs a fresh worker.
const CACHE = "books-assets-__BUILD__";
const ASSETS = "/assets/frappe_books/books/assets/";

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
	event.waitUntil(removeOldCaches().then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
	const { request } = event;
	if (request.method !== "GET") return;

	if (request.mode === "navigate") {
		event.respondWith(fetch(request).catch(offlinePage));
		return;
	}

	const url = new URL(request.url);
	if (url.origin === location.origin && url.pathname.startsWith(ASSETS)) {
		event.respondWith(cacheFirst(request));
	}
});

// Push notifications (spec 0026 AC-11). FCM sends data only messages, so this worker shows each one;
// the page registers no Firebase onMessage handler, so an open /books tab never doubles it.
self.addEventListener("push", (event) => {
	const message = readPush(event);
	if (!message) return;
	event.waitUntil(
		self.registration.showNotification(message.title, {
			body: message.body,
			tag: message.tag || undefined,
			icon: ICON,
			data: { link: message.link },
		}),
	);
});

self.addEventListener("notificationclick", (event) => {
	event.notification.close();
	const link = bookLink(event.notification.data && event.notification.data.link);
	if (!link) return;
	event.waitUntil(openBooks(link));
});

const ICON = `data:image/svg+xml,${encodeURIComponent(`__ICON__`)}`;

/** The FCM data of a push: `{ data: { title, body, link, tag } }`, or those keys at the top. */
function readPush(event) {
	if (!event.data) return null;
	let payload;
	try {
		payload = event.data.json();
	} catch {
		return null;
	}
	const data = (payload && (payload.data || payload)) || {};
	const title = typeof data.title === "string" ? data.title.trim() : "";
	const link = bookLink(data.link);
	// A push with no title or a link outside /books shows nothing.
	if (!title || !link) return null;
	return {
		title,
		body: typeof data.body === "string" ? data.body : "",
		tag: typeof data.tag === "string" ? data.tag : "",
		link,
	};
}

/** A same origin path under /books/, else null. */
function bookLink(value) {
	if (typeof value !== "string" || !value) return null;
	let url;
	try {
		url = new URL(value, self.location.origin);
	} catch {
		return null;
	}
	if (url.origin !== self.location.origin || !url.pathname.startsWith("/books/")) return null;
	return url.href;
}

/** Focus an open /books tab and move it to the link, or open a new window there. */
async function openBooks(link) {
	const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
	const books = windows.find((client) => {
		const { pathname } = new URL(client.url);
		return pathname === "/books" || pathname.startsWith("/books/");
	});
	if (books) {
		const focused = await books.focus();
		try {
			await (focused || books).navigate(link);
		} catch {
			// An uncontrolled tab can't be navigated by the worker; open the link instead.
			await self.clients.openWindow(link);
		}
		return;
	}
	await self.clients.openWindow(link);
}

async function removeOldCaches() {
	const names = await caches.keys();
	const old = names.filter((name) => name.startsWith("books-assets-") && name !== CACHE);
	await Promise.all(old.map((name) => caches.delete(name)));
}

async function cacheFirst(request) {
	const cache = await caches.open(CACHE);
	const cached = await cache.match(request);
	if (cached) return cached;

	const response = await fetch(request);
	if (response.ok) await cache.put(request, response.clone());
	return response;
}

function offlinePage() {
	const html = `<!doctype html>
<html lang="en">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Offline · RareBooks</title>
<style>
	:root { color-scheme: light dark; font-family: system-ui, sans-serif; }
	body { margin: 0; min-height: 100svh; display: grid; place-items: center; padding: 24px; box-sizing: border-box; text-align: center; }
	h1 { font-size: 18px; margin: 16px 0 8px; }
	p { margin: 0 0 20px; color: #7c7c7c; font-size: 14px; }
	button { font: inherit; font-size: 14px; padding: 8px 16px; border-radius: 8px; border: 0; background: #171717; color: #fff; }
	@media (prefers-color-scheme: dark) { button { background: #fff; color: #171717; } }
</style>
<main>
	<div style="width: 56px; margin: auto">__ICON__</div>
	<h1>You're offline</h1>
	<p>RareBooks needs a connection. Your data is safe on the server.</p>
	<button onclick="location.reload()">Try again</button>
</main>
</html>`;
	return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8" } });
}
