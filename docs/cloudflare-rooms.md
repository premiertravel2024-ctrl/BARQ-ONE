# BARQ ONE Cloudflare rooms (free tier)
The root wrangler.jsonc deploys the barq-one Worker from this repository. The Worker is **only a room signaling service**; BARQ's local Windows administrative API is never exposed. Room data is a two-hour SQLite Durable Object; guest invitations include a random URL token and six-digit code, and room creation is limited per connecting IP.

Cloudflare Dashboard > Workers & Pages > barq-one > Settings > Builds must use **premiertravel2024-ctrl/BARQ-ONE**, branch **main**, root **/**, deploy command **npx wrangler deploy**. Automatic builds on push may need to be enabled. Enable production workers.dev domain.

Health: https://barq-one.ashraf-mohamed.workers.dev/health
A blank homepage is replaced with a JSON service status.

The Windows client defaults to BARQ_WATCH_RELAY_URL=https://barq-one.ashraf-mohamed.workers.dev. This relay supports peer-to-peer WebRTC and STUN for NAT traversal. **It does not provide a free TURN media relay**; some networks will fail to connect, and Spotify/Anghami embeds depend on each provider's playback/licensing rules. The relay carries signaling/chat only and never receives or stores your films or music.

Do not put a shared create token in the EXE. Public creation uses a server-side per-IP quota (8 room attempts per hour); add Turnstile/Auth and stronger anti-abuse controls before inviting untrusted users or scaling. Never store private room URLs in logs. Joining from a browser works; the host can control the room inside BARQ.
