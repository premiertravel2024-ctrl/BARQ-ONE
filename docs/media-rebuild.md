# BARQ ONE media rebuild

## Catalogue
Cinema uses real TMDB metadata via the local API. Set `TMDB_READ_TOKEN` and restart BARQ, or use Cinema → setup with the TMDB **API Read Access Token**. The setup validates the token then stores it using the OS credential vault. No token is stored in JavaScript/localStorage or committed to source.

Browse movies, TV and Japanese animation with pagination (up to TMDB's 500-page endpoint limit), search, genre/year/rating filters, trending, popular, recent and top-rated collections. Search filters unsupported by TMDB are clearly identified as current-page filters. Favourites and watchlists persist locally. Movie posters do not provide playable streams. Room playback uses selected files or authorized media URLs.

## Personal music
Import files or a folder from the native Windows picker. Up to 5,000 files are indexed per import, with title/artist/album/duration and embedded JPEG/PNG covers read by Mutagen. Original files stay in place; moving a file requires reimport. Local paths stay in the backend manifest. The browser receives only IDs and metadata. Playlists, favourites, queue, recent history, volume and playback position persist on this device. Playback does not autoplay after a restart. Codec support depends on Windows WebView2.

## Rooms
Official Spotify and Anghami players are independent provider players. Each participant may need to sign in or press Play; synchronized official-provider playback is not claimed. Local media uses the existing WebRTC capture path. Reconnection retries transient signaling failures up to five times. Chat won't silently clear a draft when the peer is absent. Both local and Cloudflare paths normalize guest chat text.

Cloudflare signaling alone cannot relay media through restrictive NAT/firewalls. Configure `BARQ_TURN_URLS` (comma-separated turn/turns URLs with explicit port) and `BARQ_TURN_SECRET` (at least 32 characters) as Worker secrets, using a TURN service configured with the same shared secret. Authenticated room participants receive HMAC credentials lasting 7,500 seconds; the shared secret is never sent to browsers. Without it, STUN/direct connectivity remains available and the UI explains relay failures. A separately deployed relay remains supported.

## Wallpaper repairs
Applying an integrated wallpaper now looks up the native manifest instead of Lively's legacy manifest. Windows x64 APIs use pointer-sized HWND signatures and validate SetParent/SetWindowPos. The helper reports readiness only after desktop attachment and actual media playback/load. MP4, WebM and GIF are accepted; unsupported formats are not offered. Child-process diagnostics are in the user's wallpaper data directory as `engine.log`.

## Validation and limits
`tests/test_cinema_music_rebuild.py` exercises real tagged WAV import, deduplication, unavailable files, native route selection, remote catalogue filters, missing credentials, cache behavior and rate-limit backoff. Cloudflare tests cover chat and temporary TURN credentials. `npm run test:media-ui` uses explicitly isolated test fixtures, never production fallback catalogue data, for desktop/mobile behavior and screenshots.

Live TMDB calls require the user's token. Cross-network WebRTC, official-provider playback and visible WorkerW playback on the user's Windows desktop still require real device/service acceptance checks; a successful installer self-test alone does not prove those outcomes.
