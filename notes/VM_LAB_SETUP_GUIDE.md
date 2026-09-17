# Beginner's KVM/QEMU VM Lab Guide

This guide explains the virtual-machine setup for the university **SYN Flood
and DoS Project**. It assumes no previous virtualization knowledge. Read it
from top to bottom the first time. After that, the checklists near the end are
enough for normal use.

The goal is to create two small Linux computers inside the physical computer:

- `syn-sender`: runs our packet-building program;
- `syn-receiver`: runs a small listening server and captures the packets.

Both VMs will be connected to a private virtual network that has **no route to
the internet or physical LAN**. Crafted traffic must never be tested through
the normal Wi-Fi or Ethernet connection.

---

## 1. The four layers: KVM, QEMU, libvirt, and virt-manager

These names describe different parts of one stack. They are not four competing
VM systems that must be chosen between.

```text
You
 |
 +-- virt-manager: graphical buttons and windows
 |
 +-- virsh: terminal commands
          |
          +-- libvirt: VM management service and stored configuration
                       |
                       +-- QEMU: creates the virtual computer and devices
                                  |
                                  +-- KVM: lets its virtual CPU run efficiently
                                             on the real CPU
```

### KVM

**KVM** means Kernel-based Virtual Machine. It is part of the Linux kernel.
Modern CPUs have special virtualization support. KVM lets a VM use that support
instead of slowly simulating every CPU instruction in software.

KVM is the acceleration mechanism. It does not provide a friendly VM creation
screen, disk-image library, or day-to-day management interface by itself.

### QEMU

**QEMU** is the program that creates the virtual hardware: CPU, RAM, disk
controller, network card, display adapter, CD-ROM drive, and so on. When QEMU
uses KVM acceleration, the combination is commonly called **QEMU/KVM**.

### libvirt

**libvirt** is the management layer. It remembers VM definitions, starts QEMU
with the correct settings, manages virtual networks and disks, and provides a
consistent interface to other tools.

This guide uses the system libvirt connection:

```text
qemu:///system
```

That is important. `qemu:///system` and `qemu:///session` are two separate VM
collections. A VM visible in one may appear to be missing from the other.

### virsh

**virsh** is libvirt's command-line remote control. It is useful for checking
status, starting or stopping VMs, and diagnosing problems. For example, this
HOST command lists system VMs:

```bash
virsh -c qemu:///system list --all
```

`virsh` normally manages the VM from outside. It does not run ordinary Linux
commands inside the guest.

### virt-manager

**Virtual Machine Manager**, launched with `virt-manager`, is the graphical
front end to libvirt. The GUI and `virsh` manage the same system VMs when they
use the same `qemu:///system` connection. A change made in one is visible in
the other.

For this first setup, use virt-manager for creation and installation. Use
`virsh` for quick checks after you understand what the GUI is doing.

---

## 2. Host, guest, VM, hypervisor, and console

- **Host**: the real Ubuntu computer.
- **Guest**: an operating system running inside a VM. Debian will be our guest.
- **VM**: the complete virtual computer containing virtual hardware and a guest
  OS.
- **Hypervisor**: software that runs VMs. Here that means QEMU using KVM.
- **Console**: the VM's virtual monitor and keyboard shown by virt-manager.
- **Terminal**: a shell. Always ask, "Is this the host terminal or guest
  terminal?" before entering a command.

Commands in this document are labelled **HOST**, **SENDER VM**, **RECEIVER
VM**, or **BOTH VMs**. Do not use a VM command on the host merely because both
systems run Linux.

---

## 3. ISO, virtual CD-ROM, virtual disk, and QCOW2

### ISO image

An **ISO** file is a byte-for-byte image of an installation disc. It contains
the Debian installer and enough Debian files to begin installation. Downloading
an ISO does not install Debian.

We want the official **Debian stable amd64 netinst ISO**:

- `amd64` means 64-bit Intel/AMD PCs; it is correct for this host.
- `netinst` is a small installer image. It installs a minimal base system and
  downloads selected packages while temporary internet access is available.
- Do not select an ARM image, a Live desktop image, or a full DVD image.

Official download page:

<https://www.debian.org/CD/netinst/>

Official installation manual:

<https://www.debian.org/releases/stable/amd64/>

Use the current Debian 13 stable point release offered by the official page.
Do not depend on a version number copied from an old tutorial.

### Virtual CD-ROM drive

virt-manager can place the ISO in a VM's **virtual CD-ROM drive**. The VM sees
it like a physical computer sees an inserted installation disc. The first boot
starts the installer from this virtual disc.

After Debian is installed, eject/disconnect the ISO. Otherwise the VM may open
the installer again when it reboots. Ejecting it does **not** uninstall Debian;
the installed OS is on the virtual hard disk.

### Virtual disk and QCOW2

The VM's hard disk is normally one file on the host ending in `.qcow2`. The
guest treats it like a physical disk. QCOW2 supports sparse allocation and
snapshots. A 6 GB virtual disk does not necessarily consume 6 GB immediately;
the host file grows as data is written.

Do not open, move, rename, or delete a VM disk while its VM is running. Delete
a VM through virt-manager only after checking whether its storage should also
be deleted.

---

## 4. Confirmed state of this host

These facts were checked on 2026-09-13:

- Host OS: Ubuntu 24.04.4 LTS;
- CPU architecture: x86-64;
- `/dev/kvm` exists;
- the user `jihad` belongs to the `kvm` and `libvirt` groups;
- QEMU, libvirt, `virsh`, `virt-install`, and virt-manager are installed;
- libvirt is using QEMU 8.2.2;
- the system connection `qemu:///system` works;
- the `default` NAT network is active and starts automatically;
- an unrelated powered-off VM named `analysis-vm` already exists.

Therefore, **do not reinstall KVM/QEMU/libvirt**. Also do not modify or reuse
`analysis-vm`; it belongs to a different project.

If this document is used much later or on another computer, repeat the checks
in the troubleshooting section instead of assuming these facts remain true.

---

## 5. Our final lab design

```text
Physical Ubuntu host
|
+-- default NAT network (internet through host)
|      Used only while installing/updating the guests
|
+-- syn-lab-isolated network (no forwarding)
       |
       +-- syn-sender    192.168.150.10/24
       |
       +-- syn-receiver  192.168.150.20/24

No default gateway inside either lab VM
No DNS server needed during experiments
No bridge to physical Wi-Fi or Ethernet
```

Recommended resources for **each** VM:

| Setting | Value | Reason |
|---|---:|---|
| CPUs | 1 vCPU | More than enough for this small lab |
| RAM | 512 MiB | Lightweight command-line Debian |
| Disk | 6 GiB QCOW2 | Enough for Debian and development tools |
| Desktop | None | Saves RAM and disk space |
| Network device | virtio | Efficient Linux virtual NIC |
| Disk bus | virtio | Efficient Linux virtual disk |
| Firmware | Default | No special firmware is needed |

If the Debian installer struggles at 512 MiB, temporarily assign 768 MiB or
1 GiB. RAM assigned to a powered-off VM is not being consumed by that VM.

---

## 6. Understand the networking modes before clicking anything

### NAT: temporary setup network

The existing libvirt network named `default` uses NAT. A guest can initiate
connections to the internet through the host, while ordinary unsolicited
connections from the LAN cannot directly reach the guest.

NAT is appropriate for downloading Debian packages. It is **not** the final
network for traffic-generation tests because it has a path beyond the lab.

### Isolated libvirt network: final experiment network

An isolated libvirt network has no forwarding mode. Guests on it can talk to
each other and normally to the host-side virtual bridge, but libvirt does not
forward their traffic to the physical LAN or internet.

This is our final network. We will additionally give the guests no default
gateway. The combination gives us an obvious configuration boundary and no
normal route outward.

### Host-only

"Host-only" is terminology used by some other VM products. An ordinary
libvirt isolated network is the closest equivalent: guests can communicate
with one another and the host, but it has no external forwarding.

### Internal or no-gateway virtual network

libvirt can also create a network with no host IP address. That isolates guest
communication even further, but removes convenient host-to-guest access. It is
not necessary for the first version of this project.

### Bridged, direct, macvtap, routed, and physical adapters

These modes may put a VM directly on, or route it toward, the real LAN. Do not
use them for this project. Do not attach a physical interface, `wlan0`,
`eth0`, `enp...`, or `wlp...` to the lab.

### A subtle but important point

"Isolated" is a network configuration, not magic protection against every
mistake. A VM with two NICs—one isolated and one NAT—still has an outward path.
Before an experiment, each VM must have **only one active NIC**, connected to
`syn-lab-isolated`.

Official libvirt network reference:

<https://libvirt.org/formatnetwork.html>

### Where the virtual network devices actually live

The virtual network is made from several separate objects. They do not all
live in QEMU.

```text
SENDER VM                         PHYSICAL UBUNTU HOST                    RECEIVER VM

program                                                                  server
   |                                                                        |
guest Linux network stack                                      guest Linux network stack
   |                                                                        |
ens3                                                                     ens3
(virtual NIC seen by guest)                                  (virtual NIC seen by guest)
   |                                                                        |
QEMU virtio-net device                                          QEMU virtio-net device
   |                                                                        |
host TAP device                                                  host TAP device
(temporary name such as vnet1)                        (temporary name such as vnet2)
   \                                                                        /
    +------------------- virbr150 Linux bridge -----------------------------+
                            software switch
                         192.168.150.1 on host
                                  |
                         no forwarding to the
                         physical Wi-Fi/Ethernet
```

Read the diagram from either VM toward the middle:

1. The guest sees a network card such as `ens3`. It looks like hardware to
   Debian, but it is virtual.
2. QEMU presents that card using the efficient `virtio-net` model.
3. When the VM starts, libvirt creates a host-side **TAP interface**, usually
   named `vnet0`, `vnet1`, and so on. Think of this as the VM network cable's
   host end.
4. libvirt plugs that TAP interface into `virbr150`.
5. `virbr150` is a **Linux bridge** in the physical host's kernel. A bridge is
   a software Ethernet switch. It forwards Ethernet frames between the ports
   connected to it.
6. A frame for the receiver crosses the bridge to the receiver's TAP device,
   then QEMU delivers it through the receiver's virtual NIC.

The names `vnet0`, `vnet1`, and so on are temporary. A number may be reused or
change after a VM restarts. The stable things to rely on are the VM name, its
configured network source, and its MAC address—not a particular `vnet` number.

### What “active isolated network” means

For `syn-lab-isolated`, the words have separate meanings:

- **Active**: libvirt has created `virbr150` and the network service is ready
  for VMs to attach. It does not mean a VM is attached, and it does not mean
  packets are currently moving.
- **Persistent**: the network definition remains after the host reboots.
- **Autostart**: libvirt will activate the virtual network when its service
  starts.
- **Isolated**: its XML has no `<forward>` element, so libvirt does not provide
  a route from this bridge to the physical LAN or internet.

An active switch with no attached VM is like a powered-on physical switch with
all its Ethernet ports empty.

### Who can see traffic on an isolated network?

It is **not correct** to say that only the VMs can ever read it.

- VMs attached to this same virtual switch can exchange traffic.
- The physical host owns `virbr150`, has address `192.168.150.1`, and can
  communicate with the guests. A host administrator can also capture traffic
  on the bridge.
- A VM not attached to this network cannot normally receive its frames.
- Devices on the real Wi-Fi/Ethernet LAN cannot normally receive these frames,
  because the isolated network has no forwarding or physical bridge.
- Broadcast frames are delivered across the virtual network. Ordinary unicast
  frames are switched toward their destination port, although a privileged
  host administrator can still inspect them.

Isolation therefore means **no configured outward path**, not secrecy from the
physical host. The host controls the hypervisor and can always inspect or alter
its VMs.

### What exists on this computer right now

This snapshot was checked on 2026-09-13:

- `syn-lab-isolated` is active, persistent, and set to autostart;
- its host software switch is `virbr150` at `192.168.150.1/24`;
- its DHCP range is `192.168.150.100` through `192.168.150.199`;
- its XML has no `<forward>` element;
- it currently has no DHCP leases;
- `virbr150` reports `NO-CARRIER`, meaning no running VM cable is connected;
- `syn-sender` is powered off and configured for temporary `default` NAT;
- `syn-receiver` is currently running on temporary `default` NAT through
  `vnet0` and `virbr0`;
- neither VM is currently attached to `syn-lab-isolated`.

That last point is intentional during Debian installation. Later, after tools
are installed, both VM definitions will be changed from `default` to
`syn-lab-isolated` while powered off.

### Commands that show what currently exists

Run all commands in this subsection on the **physical HOST**.

List the VMs and see whether each virtual computer is running:

```bash
virsh -c qemu:///system list --all
```

List all libvirt networks:

```bash
virsh -c qemu:///system net-list --all
```

Explain the isolated network's state and bridge name:

```bash
virsh -c qemu:///system net-info syn-lab-isolated
```

Show its exact definition. For this lab, absence of `<forward>` is the crucial
isolation property:

```bash
virsh -c qemu:///system net-dumpxml syn-lab-isolated
```

Show which virtual network each VM is configured to use:

```bash
virsh -c qemu:///system domiflist syn-sender
virsh -c qemu:///system domiflist syn-receiver
```

How to read the important columns:

- `Source default` means the VM is using the temporary NAT network;
- `Source syn-lab-isolated` means it is using the experiment network;
- `Model virtio` identifies the emulated NIC type;
- `MAC` is that virtual NIC's Ethernet address;
- `Interface -` usually means the VM is off, so no temporary TAP exists;
- `Interface vnetN` means the running VM has a live host-side TAP device.

Show Linux bridges and live TAP ports on the host:

```bash
ip -brief link
bridge link show
```

Inspect only our lab switch:

```bash
ip address show virbr150
```

Show addresses that libvirt's DHCP service has leased to attached guests:

```bash
virsh -c qemu:///system net-dhcp-leases syn-lab-isolated
```

An empty lease table does not mean the network is broken. It can mean no guest
is attached, no guest is running, or the guests use manually assigned IP
addresses.

---

## 7. Phase A — download and verify the Debian ISO

Do this on the **HOST**.

1. Open <https://www.debian.org/CD/netinst/>.
2. Choose the official stable `amd64` netinst ISO.
3. Download the ISO and its checksum file from Debian.
4. Keep it in a clear location such as the host's `Downloads` directory.

Why verify it? A checksum detects an incomplete or altered download.

In a **HOST terminal**, enter the command below after replacing the example
path with the real ISO filename:

```bash
sha512sum /home/jihad/Downloads/debian-13.x.x-amd64-netinst.iso
```

Compare the entire printed value with the corresponding filename in Debian's
official `SHA512SUMS` file. It must match exactly. The `x.x` text above is a
placeholder; do not type it literally.

For stronger authenticity verification, follow Debian's official ISO
verification instructions linked from its download page. Never download the
ISO from an unofficial file-sharing site.

---

## 8. Phase B — create the isolated lab network

Do this in **virt-manager on the HOST** before creating the two VMs.

1. Launch **Virtual Machine Manager** from the application menu.
2. Confirm the connection shown is **QEMU/KVM – System**. If it is missing,
   select **File → Add Connection**, choose QEMU/KVM, select the system
   connection, and connect.
3. Select the system connection and open **Edit → Connection Details**.
4. Open the **Virtual Networks** tab.
5. Click `+` to create a new network.
6. Name it `syn-lab-isolated`.
7. Use IPv4 network `192.168.150.0/24`.
8. The host-side bridge address may be `192.168.150.1`.
9. DHCP may be enabled, but we will use fixed guest addresses for clarity.
10. Choose **Isolated virtual network** or ensure forwarding is set to
    **None / Isolated**. Do not choose NAT, routed, or physical forwarding.
11. Finish, start the network, and enable autostart if the GUI offers it.

GUI wording can vary slightly by virt-manager version. The defining property
is that the network has **no forwarding destination or forward mode**.

Verify it from a **HOST terminal**:

```bash
virsh -c qemu:///system net-list --all
virsh -c qemu:///system net-dumpxml syn-lab-isolated
```

Expected:

- the network is listed as active;
- its XML contains the `192.168.150.0/24` configuration;
- there is no `<forward ...>` element.

If the XML contains `<forward mode='nat'>`, it is not isolated. Do not use it
for experiments.

---

## 9. Phase C — create the sender VM

Do this in **virt-manager on the HOST**.

1. Click **Create a new virtual machine**.
2. Select **Local install media (ISO image or CD-ROM)**.
3. Browse to the verified Debian netinst ISO.
4. Let virt-manager detect Debian. If detection fails, select the newest
   available Debian entry manually.
5. Assign **512 MiB RAM** and **1 CPU**.
6. Create a **6 GiB** virtual disk.
7. Name the VM `syn-sender`.
8. Check **Customize configuration before install**.
9. In the hardware list:
   - ensure the disk uses a virtio bus when available;
   - ensure the network adapter model is virtio;
   - connect the network adapter to the existing `default` NAT network for the
     installation only;
   - keep the display and other defaults;
   - confirm the Debian ISO appears as a CD-ROM device.
10. Begin installation.

At this point, the VM boots from its virtual CD-ROM. Nothing is being written
to the host's real operating-system disk partitions; the installer writes to
the VM's QCOW2 virtual disk.

---

## 10. Debian installer choices

These choices apply to both VMs.

1. Choose **Install** rather than Graphical install to save a little memory.
2. Select the preferred language, region, and keyboard.
3. Hostname:
   - `syn-sender` for the first VM;
   - `syn-receiver` for the second VM.
4. Domain name: leave blank.
5. Create a normal user. Use a password you can remember, but do not reuse an
   important personal password.
6. Time zone: choose the correct local zone.
7. Partitioning: choose **Guided – use entire disk**.
8. Confirm that the selected disk is the small virtual disk, commonly shown as
   `/dev/vda`. It must be approximately 6 GB.
9. Choose **All files in one partition**. LVM and disk encryption are not
   needed for this disposable lab.
10. Confirm writing changes to the virtual disk.
11. Allow the package manager to use a nearby Debian mirror.
12. Package popularity survey: either answer is fine.
13. At **Software selection**:
    - uncheck **Debian desktop environment**;
    - uncheck GNOME/KDE/Xfce and any other desktop;
    - keep **standard system utilities**;
    - select **SSH server** if convenient remote access is desired.
14. Install GRUB to the offered virtual disk.
15. Finish the installation and reboot.

If the installer reports that the installation medium should be removed,
virt-manager may remove it automatically. Otherwise:

1. shut the VM down;
2. open its hardware details;
3. select the CD-ROM device;
4. disconnect/eject the ISO, without deleting the ISO file;
5. ensure the virtual disk comes before CD-ROM in the boot order.

The VM should now boot from its virtual hard disk to a text login prompt.

---

## 11. Phase D — create the receiver VM

Repeat Phases C and D as a separate installation with these changes:

- VM name and Debian hostname: `syn-receiver`;
- still use 1 vCPU, 512 MiB RAM, and a 6 GiB disk;
- use the same verified ISO;
- use the `default` NAT network temporarily during installation.

Separate installations avoid duplicate machine identities and SSH host keys.
Do not clone the running sender VM.

---

## 12. Phase E — install only the required guest tools

Do this while each VM is still attached to the temporary `default` NAT
network. Run these inside **BOTH VMs**, not on the host:

```bash
sudo apt update
sudo apt full-upgrade
sudo apt install python3 iproute2 iputils-ping tcpdump openssh-server
```

What these provide:

- `python3`: our initial implementation language;
- `iproute2`: commands such as `ip address` and `ip route`;
- `ping`: simple connectivity checks;
- `tcpdump`: packet observation on the receiver;
- `openssh-server`: optional terminal access from the host.

If the later implementation needs a compiler, add it then:

```bash
sudo apt install build-essential
```

Do not install a desktop, Kali tool collection, web server stack, Docker, or
unrelated security tools.

Shut each guest down cleanly after updates:

```bash
sudo poweroff
```

Wait until virt-manager reports **Shutoff**.

---

## 13. Phase F — remove internet access and attach the lab network

For each powered-off VM in **virt-manager on the HOST**:

1. Open the VM.
2. Open **Show virtual hardware details**.
3. Select its network interface.
4. Change **Network source** from `default` to
   `syn-lab-isolated: Isolated network`.
5. Keep the device model as `virtio`.
6. Apply the change.
7. Confirm there is exactly **one** network interface in the hardware list.

Do this for both `syn-sender` and `syn-receiver`.

Do not merely add the isolated NIC while leaving NAT attached. The NAT NIC
must be replaced or removed before experiments.

---

## 14. Phase G — assign fixed lab addresses

For the first learning session, temporary addresses are easiest and make every
step visible. They disappear on reboot, which is acceptable until the VM setup
is proven.

First, find the interface name inside **each VM**:

```bash
ip -brief link
```

The virtual Ethernet interface will often be named `ens3`, but use the real
name shown on screen. Do not blindly assume it is `ens3`.

In the **SENDER VM**, replacing `ens3` if necessary:

```bash
sudo ip address flush dev ens3
sudo ip address add 192.168.150.10/24 dev ens3
sudo ip link set ens3 up
```

In the **RECEIVER VM**:

```bash
sudo ip address flush dev ens3
sudo ip address add 192.168.150.20/24 dev ens3
sudo ip link set ens3 up
```

Do **not** add a default gateway. These addresses are for the lab subnet only.

Check inside **BOTH VMs**:

```bash
ip -brief address
ip route
```

Expected routes contain the local `192.168.150.0/24` subnet. There should be
no line beginning with `default via` during experiments.

Once everything works, these addresses can be made persistent using Debian's
installed network manager. Do that only after identifying whether the guest
uses `/etc/network/interfaces`, NetworkManager, or `systemd-networkd`; mixing
configuration systems creates confusing failures.

---

## 15. Prove connectivity and isolation before project traffic

### Test VM-to-VM communication

From the **SENDER VM**:

```bash
ping -c 3 192.168.150.20
```

From the **RECEIVER VM**:

```bash
ping -c 3 192.168.150.10
```

Both should succeed.

### Test that no normal route leaves the lab

Inside **BOTH VMs**:

```bash
ip route
ip route get 1.1.1.1
```

The second command should report that the destination is unreachable or that
there is no route. If it shows a route through a gateway, stop and inspect the
NICs before continuing.

Also check the libvirt attachment from the **HOST**:

```bash
virsh -c qemu:///system domiflist syn-sender
virsh -c qemu:///system domiflist syn-receiver
```

Each VM should have one interface whose source is `syn-lab-isolated`. Neither
should show `default`, a host bridge, or a physical interface.

### Understand what these checks prove

They prove that the configured guest path has no normal external route. They
do not authorize removing the program's own safety controls. The sender must
still use a fixed receiver address, dry-run mode, conservative rate limit, and
maximum packet count.

---

## 16. Record IP and MAC addresses for raw Ethernet frames

Our eventual `AF_PACKET` program constructs Ethernet headers, so it needs the
virtual NIC addresses.

Inside the **SENDER VM**:

```bash
ip link show
```

Record the `link/ether` address for the lab interface as the sender MAC.

Inside the **RECEIVER VM**:

```bash
ip link show
```

Record its `link/ether` address as the receiver MAC.

The final fixed lab values will therefore be:

| Field | Value |
|---|---|
| Sender IPv4 | `192.168.150.10` |
| Receiver IPv4 | `192.168.150.20` |
| Sender MAC | copy from `syn-sender` |
| Receiver MAC | copy from `syn-receiver` |
| Interface name | copy from each VM |

MAC addresses can change if a NIC is deleted and recreated. Recheck them after
changing virtual hardware.

---

## 17. Take clean snapshots

A snapshot is a restore point for a VM. Take one for each powered-off VM after:

- Debian is installed;
- required tools are installed;
- the ISO is ejected;
- NAT has been removed;
- the isolated NIC is attached;
- VM-to-VM connectivity and lack of an external route are verified.

In virt-manager:

1. shut down the guest;
2. open the VM;
3. open the snapshot view;
4. create a snapshot named `clean-isolated-baseline`;
5. describe what has been verified.

Never assume a snapshot replaces a backup of important project source files.
Snapshots are convenient lab rollback points and remain tied to the VM's
storage.

---

## 18. Safe daily workflow

### Start a session

On the **HOST**:

```bash
virsh -c qemu:///system net-list --all
virsh -c qemu:///system start syn-receiver
virsh -c qemu:///system start syn-sender
virsh -c qemu:///system list --all
```

Then inside both guests, reapply the temporary addresses from Phase G if they
have not yet been made persistent.

Before transmitting anything, perform the isolation checks:

```bash
ip route
ip route get 1.1.1.1
```

### Observe first, transmit second

On the **RECEIVER VM**, start a bounded packet capture on the lab interface:

```bash
sudo tcpdump -ni ens3 -c 20 'tcp'
```

Replace `ens3` with the actual interface name. `-c 20` stops after 20 matching
packets so the capture does not run forever.

Only after capture is ready should a tightly limited project test run on the
sender.

### End a session

Inside **BOTH VMs**:

```bash
sudo poweroff
```

On the **HOST**, confirm both are off:

```bash
virsh -c qemu:///system list --all
```

Prefer a guest shutdown over forcibly powering off a running VM.

---

## 19. Essential virsh commands

All commands in this table run on the **HOST**.

| Goal | Command |
|---|---|
| List all VMs | `virsh -c qemu:///system list --all` |
| Start sender | `virsh -c qemu:///system start syn-sender` |
| Ask sender to shut down | `virsh -c qemu:///system shutdown syn-sender` |
| See VM information | `virsh -c qemu:///system dominfo syn-sender` |
| See attached NICs | `virsh -c qemu:///system domiflist syn-sender` |
| See virtual networks | `virsh -c qemu:///system net-list --all` |
| Inspect lab network | `virsh -c qemu:///system net-dumpxml syn-lab-isolated` |
| Start lab network | `virsh -c qemu:///system net-start syn-lab-isolated` |
| Enable network at boot | `virsh -c qemu:///system net-autostart syn-lab-isolated` |
| Open a text console | `virsh -c qemu:///system console syn-sender` |

To leave a `virsh console`, press `Ctrl+]`. A blank console does not
necessarily mean the VM failed; the guest may not have a serial console
configured. Use virt-manager's graphical console in that case.

Avoid these until their consequences are understood:

- `virsh destroy`: this means pull the virtual power plug, not delete the VM;
- `virsh undefine`: remove a VM definition;
- storage deletion options: may permanently delete the guest disk;
- editing network XML blindly: may break isolation.

---

## 20. When temporary internet access is needed later

Do not add NAT while the packet experiment is running.

Safe maintenance sequence:

1. stop project programs and packet captures;
2. shut down both VMs;
3. attach **one VM at a time** to `default` NAT in virt-manager;
4. boot it and perform the update or package installation;
5. shut it down;
6. replace NAT with `syn-lab-isolated` again;
7. confirm it has exactly one NIC;
8. repeat for the other VM if necessary;
9. redo all isolation checks before any crafted-packet test.

Never solve a package-download problem by leaving a second NAT NIC attached.

---

## 21. Common problems and what they mean

### "No active connection" or the VM list is mysteriously empty

Likely cause: virt-manager or `virsh` is using `qemu:///session` instead of
`qemu:///system`.

Check on the **HOST**:

```bash
virsh -c qemu:///system list --all
```

In virt-manager, connect to **QEMU/KVM – System**.

### Permission denied for `/dev/kvm` or libvirt socket

Check on the **HOST**:

```bash
ls -l /dev/kvm
id
```

The current host was already verified to have the correct `kvm` and `libvirt`
group memberships. If membership was just added on another machine, log out
and back in before retesting.

### VM is extremely slow and says TCG instead of KVM

QEMU is probably emulating the CPU instead of using KVM acceleration. Confirm
that virtualization is enabled in BIOS/UEFI, `/dev/kvm` exists, and the VM's
configuration uses KVM.

### The installer starts again after installation

The ISO is still mounted or CD-ROM precedes the disk in boot order. Power off
the VM, eject/disconnect the ISO in hardware details, and boot from the virtual
disk.

### Debian cannot download packages during installation

Confirm the installation NIC is temporarily attached to `default` NAT and that
the libvirt default network is active:

```bash
virsh -c qemu:///system net-list --all
```

This host's `default` network was active when checked. Do not change the final
lab network to NAT just to hide an installation-stage problem.

### Sender cannot ping receiver

Check, in this order:

1. both VMs are running;
2. both NICs use `syn-lab-isolated`;
3. both guest interfaces are `UP`;
4. addresses are `192.168.150.10/24` and `192.168.150.20/24`;
5. both use the same `/24` prefix;
6. no firewall rule is rejecting ICMP;
7. the isolated network is active.

Useful guest command:

```bash
ip -brief address
```

Useful host commands:

```bash
virsh -c qemu:///system domiflist syn-sender
virsh -c qemu:///system domiflist syn-receiver
virsh -c qemu:///system net-list --all
```

### The guest can still access the internet

Stop before testing. Look for:

- a second virtual NIC;
- a NIC still connected to `default`;
- a default route inside the guest;
- a `<forward>` element in the lab network XML.

Correct all four and repeat the isolation checks.

### Raw socket returns "Operation not permitted"

Raw packet sockets require elevated network capability inside the **sender
VM**. During early stages, serialize and test the packet bytes without opening
a raw socket. When the project reaches its bounded transmission stage, run
only the required sender command with guest-side privilege. Do not run the
whole development environment as root and do not grant privileges on the host.

### VM window closes but VM remains running

Closing the console window does not necessarily shut down the computer. Check
virt-manager or:

```bash
virsh -c qemu:///system list --all
```

Shut down from inside the guest or use `virsh shutdown`.

### Changes disappeared after reboot

Addresses entered with `ip address add` are deliberately temporary. Reapply
them, or configure them persistently after identifying the guest's networking
service.

---

## 22. Safety rules specific to this project

1. Use only systems and virtual networks owned by the project group.
2. Never use bridged networking for generated traffic.
3. Never target a public IP, university service, home router, another student's
   computer, or any machine outside this isolated lab.
4. During experiments, each VM has one NIC: `syn-lab-isolated`.
5. No guest default gateway is needed.
6. The sender program must have:
   - a fixed lab-only target;
   - dry-run as the default;
   - conservative rate limiting;
   - a small maximum packet count;
   - clear output showing the chosen interface and destination.
7. Complete and test packet serialization before enabling transmission.
8. Keep captures bounded and stop them after each observation.
9. Take a clean snapshot before privileged packet work.
10. If an isolation check gives an unexpected result, stop. Do not "try one
    packet" to see what happens.

---

## 23. One-page build checklist

### Host preparation

- [x] Ubuntu host is x86-64.
- [x] `/dev/kvm` exists.
- [x] User belongs to `kvm` and `libvirt`.
- [x] QEMU, libvirt, virsh, and virt-manager are installed.
- [x] Use `qemu:///system`.
- [ ] Download official Debian stable amd64 netinst ISO.
- [ ] Verify ISO checksum.

### Network preparation

- [ ] Create `syn-lab-isolated` as `192.168.150.0/24`.
- [ ] Ensure it has no forwarding mode.
- [ ] Start it and optionally enable autostart.

### VM installation

- [ ] Install `syn-sender`: 1 vCPU, 512 MiB RAM, 6 GiB disk, no desktop.
- [ ] Install `syn-receiver`: same resources, separate installation.
- [ ] Use `default` NAT only during installation and updates.
- [ ] Install Python, `iproute2`, ping, tcpdump, and optional SSH.
- [ ] Eject the ISO after installation.

### Final isolation

- [ ] Power off both VMs.
- [ ] Replace NAT with `syn-lab-isolated` on both.
- [ ] Confirm exactly one NIC per VM.
- [ ] Assign `.10` to sender and `.20` to receiver.
- [ ] Confirm sender and receiver can ping each other.
- [ ] Confirm both guests have no default route.
- [ ] Confirm route lookup to `1.1.1.1` fails.
- [ ] Confirm `domiflist` shows only `syn-lab-isolated`.
- [ ] Record both MAC addresses and interface names.
- [ ] Take `clean-isolated-baseline` snapshots.

---

## 24. What comes after this guide

Once every checkbox above is complete, virtualization setup is finished. The
next work belongs to the project itself:

1. test the checksum function with known bytes;
2. build TCP, IPv4, and Ethernet headers as byte buffers;
3. verify the complete 54-byte frame without sending it;
4. capture a normal reference packet on the receiver;
5. transmit one bounded frame inside the isolated lab;
6. compare the captured fields with the expected fields;
7. only then consider a conservative multi-packet demonstration.

You should not need to redesign the VM stack while working through those
stages. If something later appears to be a virtualization problem, first use
the daily checklist and troubleshooting section rather than reinstalling the
entire stack.
