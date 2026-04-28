# Tailscale runbook — homelab + friend access

Ship the EQ2 server (and the Satisfactory dedicated server, and anything
else local) over a Tailscale overlay so a small group of friends can
connect without exposing UDP game ports to the public internet.

The friend-side experience is genuinely set-and-forget: install
Tailscale once, accept an invite once, point a game client at the
friend's stable `100.x.y.z` peer address. After that, Tailscale runs
as a system service across reboots forever.

## Architecture

Three machines on this homelab need Tailscale installed:

| Host | Why |
|---|---|
| Homelab host (CachyOS, runs the Docker stack) | The EQ2 server lives here. Its tailnet IP becomes the EQ2 world IP that all clients (host, VMs, friends) connect to. |
| Satisfactory VM | Hosts the Satisfactory dedicated server. Friend connects to the VM's tailnet IP : UDP 7777. |
| GM EQ2 client VM (`eq2-gm-vm`) | The GM client needs to reach the EQ2 world by the same tailnet IP everyone else uses, so it joins the tailnet rather than relying on libvirt-bridge routing. |

Plus the friend's machine — their own `100.x.y.z` becomes peer-routed
to the host and the Satisfactory VM.

## What's already done

On the host:

```bash
sudo pacman -S tailscale          # done
sudo systemctl enable --now tailscaled   # done
```

Pending (needs an interactive browser auth, can't be scripted from a
remote shell): `sudo tailscale up`.

## When you're home — host

1. From the host's local terminal:

   ```bash
   sudo tailscale up
   ```

   It prints a URL. Open it in a browser, sign in (Google / Microsoft /
   passkey / email), accept the device into your tailnet.

2. Note the assigned IP:

   ```bash
   tailscale ip -4
   ```

   Pin this somewhere — it's the address every game client will use.
   Doc references below call it `<HOST_TAILNET_IP>`.

3. Tell me the IP and I'll do the EQ2 server reconfiguration step
   (binding update + `login_worldservers.ip_address`) — see "Server
   reconfiguration" below for the actual commands.

## Satisfactory VM

```bash
# inside the Satisfactory VM (CachyOS or whatever it's running):
sudo pacman -S --needed tailscale
sudo systemctl enable --now tailscaled
sudo tailscale up
tailscale ip -4
```

That's the address you give your friend for the Satisfactory client
(`<SATIS_TAILNET_IP>:7777`).

The Satisfactory dedicated server already binds `0.0.0.0` by default,
so no application config change is needed — the tailnet interface
will just start receiving traffic.

## GM EQ2 client VM (`eq2-gm-vm`)

Same three commands inside the VM:

```bash
sudo pacman -S --needed tailscale
sudo systemctl enable --now tailscaled
sudo tailscale up
```

The GM client doesn't need its tailnet IP for anything externally
visible — installing Tailscale here is purely so the VM can reach the
host's tailnet IP when the EQ2 login redirects it to the world. Without
this, login redirects to `<HOST_TAILNET_IP>` would fail from inside
the VM (Tailscale by default only accepts traffic from tailnet peers).

## Server reconfiguration (after host has tailnet IP)

Three changes on the host once `<HOST_TAILNET_IP>` is known:

1. Add a tailnet bind to `docker/docker-compose.override.yaml` for the
   `eq2emu-server` service (alongside the existing 127.0.0.1 and
   192.168.122.1 binds):

   ```yaml
       - "<HOST_TAILNET_IP>:${WORLD_CLIENT_PORT}:${WORLD_CLIENT_PORT}/udp"
       - "<HOST_TAILNET_IP>:${LOGIN_CLIENT_PORT}:${LOGIN_CLIENT_PORT}/udp"
   ```

2. Update `docker/.env`:

   ```
   IP_ADDRESS=<HOST_TAILNET_IP>
   ```

3. Update the live login DB so the next client login picks up the new
   advertised world IP without waiting for a container recreate:

   ```bash
   docker exec docker-eq2emu-server-1 \
       mysql -h mysql -u "$EQ2LS_DB_USER" -p"$EQ2LS_DB_PASSWORD" "$EQ2LS_DB_NAME" \
       -e "UPDATE login_worldservers SET ip_address='<HOST_TAILNET_IP>' WHERE id=1;"
   ```

4. Recreate the container so the new bind takes effect:

   ```bash
   cd docker && docker compose up -d eq2emu-server
   ```

   ~10 seconds of disconnect for any active player. Verify after with:

   ```bash
   ss -ulnp | grep -E ':9001|:9100'
   ```

   Should show three binds for each port (127.0.0.1, 192.168.122.1,
   `<HOST_TAILNET_IP>`).

After this, every EQ2 client connects to `<HOST_TAILNET_IP>:9100` for
login regardless of where it lives. Existing host client and GM VM
client configs can stay pointed at their previous addresses
(127.0.0.1 / 192.168.122.1) since those listeners stay bound — but
the redirect target the login server hands out becomes the tailnet IP.

## Inviting a friend

1. On the host, open `https://login.tailscale.com/admin/machines` →
   "Invite users." Enter the friend's email. They get a one-click
   link to join your tailnet under their own identity (no shared
   credentials).

2. They run, on their CachyOS box:

   ```bash
   sudo pacman -S --needed tailscale
   sudo systemctl enable --now tailscaled
   sudo tailscale up
   ```

   Click the URL, accept the invite. Done. Tailscale autostarts on
   reboot and stays connected from then on.

3. They get game IPs from you:
   - **EQ2**: set `cl_ls_address = <HOST_TAILNET_IP>` in
     `eq2_default.ini`. They see "BakerWorld" in the server list.
   - **Satisfactory**: connect to `<SATIS_TAILNET_IP>:7777`.

   That's it on their side — for any game, ever. Future homelab
   services can be reached the same way without the friend touching
   anything.

## Verification

From the friend's machine (or the host with `--exit-node-allow-lan-access`):

```bash
tailscale ping <HOST_TAILNET_IP>           # < 100ms is healthy
nc -zuv <HOST_TAILNET_IP> 9100             # UDP login port reachable
nc -zuv <SATIS_TAILNET_IP> 7777            # Satisfactory reachable
```

In-game, both EQ2 server browse and Satisfactory client connect should
succeed.

## Troubleshooting

- **Friend behind CGNAT**: Tailscale's DERP relays handle this
  automatically, no action. May add 20-50 ms latency vs. direct.
- **Auth expired** (rare): `sudo tailscale up` again. Re-runs the
  device check, doesn't lose the IP.
- **Port shows bound but client can't connect**: confirm the host's
  Tailscale firewall isn't dropping — by default it accepts traffic
  from tailnet peers on every port, but if you've turned on `tailscale
  serve` or shields-up mode that changes.
- **Friend's client connects to login but hangs at "world select"**:
  the redirect target (`login_worldservers.ip_address`) isn't
  reachable from them. Re-check that the row was updated to
  `<HOST_TAILNET_IP>`.
- **Want to remove a friend**: admin console → Machines → revoke
  their device. Their tailnet IP stops resolving immediately.

## Tear-down

If you ever drop Tailscale and revert to the libvirt-bridge layout:

1. `sudo tailscale logout` on each machine, then
   `sudo systemctl disable --now tailscaled` and `sudo pacman -Rns tailscale`.
2. Set `IP_ADDRESS=192.168.122.1` back in `docker/.env`, restore the
   `login_worldservers.ip_address` value, recreate the container.
3. Friend goes back to having no remote access — that's the cost.
