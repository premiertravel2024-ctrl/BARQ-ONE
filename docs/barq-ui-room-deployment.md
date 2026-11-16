# BARQ ONE — Cloudflare room deployment

The Windows EXE and the Cloudflare guest room web page are separate deployments. A new BARQ EXE alone will not update the phone view of an invited guest.

The BARQ Rooms Cloudflare Deployment workflow validates the source. It deploys the production Worker only when both GitHub Actions secrets are configured:

- CLOUDFLARE_API_TOKEN: narrow scope for editing the BARQ Worker and Durable Objects
- CLOUDFLARE_ACCOUNT_ID: Cloudflare account owning the barq-one Worker

Without those secrets, GitHub Actions reports explicitly that deployment has NOT happened. Keep tokens private and out of source control.

The deployment performs a real /health/rooms Durable Objects probe. It cannot validate peer-to-peer WebRTC across different routers or control music service subscriptions.

Design reference links:
- Automation: https://dribbble.com/shots/27576358--Product-design-for-weather-dashboard-platform-Hyperactive
- Music: https://dribbble.com/shots/15149633-Music-Player-Desktop-App
- Cinema: https://dribbble.com/shots/26450572-Vibeflix-Movie-Streaming-Ui-Kit
- Live wallpapers: https://dribbble.com/shots/27549108-Music-Streaming-Platform-UI-UX-Design

The design takes inspiration from layout principles, not copyrighted assets. Actual foreign film, series and anime artworks are showcased only as visual browsing references. BARQ streams user-provided authorized media, never copyrighted movies from the catalogue.
