# GM-account EQ2 client VM

A dedicated KVM guest that runs an EQ2 client logged into a separate
GM-flagged account. Keeps GM authority off the operator's daily-driver
character so admin actions are deliberate, and gives a clear place to
hand the keys to a trusted friend later if needed.

## Why a VM, not just a second client on the host

- **Account isolation** — the GM client lives in its own home
  directory / Steam profile / Wine prefix. No risk of muscle memory
  using GM commands on the personal account.
- **Snapshots** — virt-manager can checkpoint the install once it's
  configured; if a Wine update breaks something we revert in seconds.
- **Resource cap** — the VM is bounded to 4GB / 2 vCPU so a runaway
  client can't starve the rest of the box.

## Spec

| Setting | Value | Why |
|---|---|---|
| Hypervisor | KVM + libvirt + virt-manager | already in use on host; no new tooling |
| Guest | Arch Linux (netinst) | matches host distro family; trivial Wine install via `pacman` |
| RAM | 4096 MB | EQ2 client + Wine ≈ 2-3 GB; 4 GB gives breathing room |
| vCPU | 2 | client is single-thread bound; second core for OS |
| Disk | 50 GB qcow2 (sparse) | EQ2 install ≈ 12 GB + Wine + headroom |
| GPU | virtio-gpu with VirGL | OpenGL accel for Wine's DX9-on-GL translation |
| Network | libvirt default (NAT) | guest gets `192.168.122.x`, reaches host on `192.168.122.1` |
| Display | virt-manager SPICE console | local-only access, no SPICE port published |

## Server-side prep (already done in `infra/expose-game-ports-libvirt`)

The eq2emu-server container now binds the game UDP ports on
`192.168.122.1` in addition to `127.0.0.1`, and the advertised world
IP in `login_worldservers.ip_address` is set to `192.168.122.1`. Both
the host's existing client and any libvirt guest can reach that IP, so
no extra plumbing is needed inside the guest.

## Build steps

### 1. Stage the install media (one-time)

```bash
sudo curl -L -o /var/lib/libvirt/boot/archlinux-x86_64.iso \
    https://geo.mirror.pkgbuild.com/iso/latest/archlinux-x86_64.iso
```

### 2. Create the disk image

```bash
sudo qemu-img create -f qcow2 -o preallocation=metadata \
    /var/lib/libvirt/images/eq2-gm-vm.qcow2 50G
```

### 3. Define the VM

```bash
sudo virt-install \
  --connect qemu:///system \
  --name eq2-gm-vm \
  --memory 4096 \
  --vcpus 2 \
  --cpu host-passthrough \
  --os-variant archlinux \
  --disk path=/var/lib/libvirt/images/eq2-gm-vm.qcow2,bus=virtio \
  --cdrom /var/lib/libvirt/boot/archlinux-x86_64.iso \
  --network network=default,model=virtio \
  --graphics spice,gl=on \
  --video virtio,accel3d=yes \
  --channel spicevmc \
  --noautoconsole
```

This boots the VM from the ISO. Open virt-manager, attach the console,
and run through the standard Arch installer (`archinstall` is the
quick path).

### 4. Inside the guest — Arch base + desktop

```bash
# during archinstall:
#   - profile: minimal
#   - packages: xorg xfce4 wine-staging lutris steam pipewire wireplumber
#     openssh sudo nano vim networkmanager
#   - bootloader: systemd-boot
#   - user: gm (with sudo)

sudo systemctl enable --now NetworkManager
```

### 5. Install EQ2 in Wine

```bash
# as the gm user
lutris  # GUI: install Steam → install EverQuest II Free-to-Play
```

Wine prefix tweaks that were needed historically (verify against
host's working config first):

```bash
WINEPREFIX=~/.local/share/wineprefixes/eq2 winetricks dotnet48 corefonts vcrun2019
```

### 6. Point the client at the homelab

After EQ2 install, edit `eq2_default.ini` in the EQ2 install dir:

```ini
cl_ls_address = 192.168.122.1
```

Restart the client and the homelab world should appear in the server
list as **BakerWorld**.

### 7. Create the GM account

On the host (one-shot, separate from the VM):

```bash
# look up real password column name on this build
docker exec docker-eq2emu-server-1 mysql -h mysql -u eq2ls -p"$EQ2LS_DB_PASSWORD" eq2ls \
  -e "INSERT INTO account (name, passwd, account_enabled) VALUES
      ('gmtoolkit', SHA2('CHOOSE_A_STRONG_PASSWORD', 512), 1);"
```

Then in the world DB, flag the account as admin (status / admin level
location varies by build — `account` table on the world side, or a
flag column on `characters` once one is created). Confirm the column
name with `SHOW COLUMNS FROM account` on the world DB and set the
status field to a value ≥ 100. We can wire this up cleanly in a
follow-up once the VM is past the Arch install.

## Operational notes

- **Don't snapshot mid-zone.** virt-manager VM-state snapshots while
  EQ2 is connected will desync the client. Camp first.
- **VM clock can drift.** Add `--clock=offset='localtime'` if you see
  Wine complaining about cert expiry.
- **No SPICE on a public interface.** Default `qemu:///system` SPICE
  is on a Unix socket — local virt-manager only. Don't change.
- **Backups.** The qcow2 lives in the default libvirt pool. Add it to
  the homelab's backup script when we set one up in Phase 2.

## Tear-down

```bash
sudo virsh shutdown eq2-gm-vm
sudo virsh undefine eq2-gm-vm --remove-all-storage
```
