# BARQ Watch Together hosted relay

The relay serves guest pages and WebSocket signaling. It does not serve BARQ's private API. Run one relay process per endpoint because active rooms exist in memory. A process restart closes active rooms.

## Server

A signaling container can be built from the repository root with
`docker build -f deploy/watch-relay/Dockerfile -t barq-watch-relay .`.
Use a runtime environment file with the server variables below and map port 8092
to the local HTTPS reverse proxy. TURN is a separate service.

1. Provision an Internet-reachable host, a DNS name and a valid HTTPS certificate. Run `python -m uvicorn services.watch_relay:app --host 127.0.0.1 --port 8092 --workers 1 --no-access-log` using a Python environment with FastAPI, Uvicorn and websockets. Reverse-proxy the public hostname to this service with WebSocket upgrades on HTTPS port 443. Disable request query-string logging in the proxy to avoid recording invitation tokens. Only this dedicated service should be exposed.
2. Provision coturn or a compatible TURN server using the TURN REST long-term authentication scheme. Ensure its listener and relay port range are reachable, and configure UDP plus TCP/TLS as appropriate for the networks served. Configure your TURN server to block relaying private/internal destination ranges. Set its realm, TLS certificate for secure TURN URLs, quotas and a randomly generated shared secret.
3. Set the following environment variables on the relay process. Use independently generated secrets of at least 32 characters. The TURN secret belongs on the relay and TURN servers.

   ```dotenv
   BARQ_RELAY_CREATE_TOKEN=<random room creation token>
   BARQ_TURN_SECRET=<coturn static-auth-secret>
   BARQ_TURN_URLS=turn:turn.example.com:3478?transport=udp,turns:turn.example.com:5349?transport=tcp
   ```

4. Confirm that `GET /health` reports ready. Then create a room from BARQ, open the invitation on another network and verify playback with TURN and with a direct connection. Internet room creation is capped at 64 active rooms per relay process. Put an additional request limit in the reverse proxy for `POST /api/rooms`.

## BARQ desktop

On trusted host installations, set `BARQ_WATCH_RELAY_URL` to the public HTTPS origin and `BARQ_WATCH_RELAY_TOKEN` to the server's room creation token. Restart BARQ and create an internet room. Installations that join via BARQ need the relay URL configured, and do not need the room creation token. A guest can open the browser link with no BARQ configuration.

The relay sends short-lived TURN credentials only after each participant proves possession of their room credentials. Room creation and TURN secrets must not be embedded in distributed installers. Use one test room across two different networks before distributing a deployment to users.
