/* Scent Scout offline copy.
   - The page and the prices open straight from the phone's saved copy, so the site appears
     instantly after the first visit, even with a weak signal or none.
   - A fresh copy is fetched in the background every time. When the prices have changed, the
     open page is told ("prices-updated") and swaps them in; a new version of the page itself is
     used the next time the site opens ("app-updated").
   - Photos, icons and other files are kept once fetched. Anything outside /scent-scout/ (the
     Neon Inc sign-in, Google, store sites) is never touched. */
const CACHE = "scentscout-v1";
const SHELL = ["./", "./manifest.webmanifest", "./favicon.svg", "./icons/icon-192.png", "./icons/apple-touch-icon.png"];
const DATA = "data/prices.json";
const SCOPE = new URL(self.registration.scope).pathname;

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith("scentscout-") && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin || !url.pathname.startsWith(SCOPE)) return;
  if (url.pathname === SCOPE + DATA) return e.respondWith(savedThenFresh(e, SCOPE + DATA, () => fetch(SCOPE + DATA, { cache: "no-cache" }), "prices-updated"));
  if (req.mode === "navigate") return e.respondWith(savedThenFresh(e, SCOPE, () => fetch(req), "app-updated"));
  e.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      if (res.ok && res.type === "basic") { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
      return res;
    }))
  );
});

// Answer from the saved copy straight away (when there is one) and refresh it in the background.
function savedThenFresh(event, key, load, message) {
  return caches.open(CACHE).then((cache) => cache.match(key).then((saved) => {
    const update = load().then((res) => {
      if (!res.ok) return res;
      const changed = saved && differs(saved, res);
      return cache.put(key, res.clone()).then(() => { if (changed) tell(message); return res; });
    });
    if (saved) { event.waitUntil(update.catch(() => {})); return saved; }
    return update.catch(() => Response.error());
  }));
}

function differs(a, b) {
  const tag = (r) => r.headers.get("etag") || r.headers.get("last-modified") || r.headers.get("content-length") || "";
  return tag(a) !== tag(b);
}

function tell(type) {
  self.clients.matchAll({ type: "window" }).then((cs) => cs.forEach((c) => c.postMessage({ type })));
}
