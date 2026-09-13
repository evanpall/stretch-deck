// Stretch Deck service worker — bump SHELL_CACHE on every deploy of index.html
// so returning phones pick up the new shell instead of a stale cached copy.
var SHELL_CACHE = "stretchdeck-shell-v4";
var VIDEO_CACHE = "stretchdeck-videos-v1";

var SHELL_FILES = [
  "./",
  "./index.html",
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png",
  "./icon-512-maskable.png"
];

self.addEventListener("install", function(event){
  event.waitUntil(
    caches.open(SHELL_CACHE).then(function(cache){ return cache.addAll(SHELL_FILES); })
      .then(function(){ return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function(event){
  event.waitUntil(
    caches.keys().then(function(names){
      return Promise.all(names.map(function(name){
        if(name !== SHELL_CACHE && name !== VIDEO_CACHE) return caches.delete(name);
      }));
    }).then(function(){ return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function(event){
  var req = event.request;
  if(req.method !== "GET") return;
  var url = new URL(req.url);
  if(url.origin !== self.location.origin) return; // leave cross-origin (fonts, reel links) alone

  var isVideo = /^\/videos\//.test(url.pathname) || url.pathname.indexOf("/videos/") !== -1;

  if(isVideo){
    event.respondWith(
      caches.open(VIDEO_CACHE).then(function(cache){
        return cache.match(req).then(function(hit){
          if(hit) return hit;
          // Video elements issue Range requests once seeking/streaming kicks in.
          // Cache Storage rejects 206 Partial Content, so only ever cache a full 200 response.
          return fetch(req).then(function(res){
            if(res.status === 200) cache.put(req, res.clone()).catch(function(){});
            return res;
          });
        });
      })
    );
    return;
  }

  // App shell: cache-first, refresh cache in the background when online.
  event.respondWith(
    caches.match(req).then(function(hit){
      var network = fetch(req).then(function(res){
        if(res.status === 200){
          caches.open(SHELL_CACHE).then(function(cache){ cache.put(req, res.clone()).catch(function(){}); });
        }
        return res;
      }).catch(function(){ return hit; });
      return hit || network;
    })
  );
});
