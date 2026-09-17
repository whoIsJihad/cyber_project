# Your two-VM lab

This is the small private network for the project. It has two Debian virtual
machines (VMs):

| VM             | Job                             | Fixed address    | Login name |
| -------------- | ------------------------------- | ---------------- | ---------- |
| `syn-sender`   | Runs the sender program later   | `192.168.150.10` | `snd`      |
| `syn-receiver` | Runs Nginx and observes traffic | `192.168.150.20` | `recv`     |

The virtual network is called `syn-lab-isolated`. It is a private software
switch inside the physical host. It lets the host and these two VMs talk to one
another. It does not forward traffic to the Internet or the home/university
network.

## Why SSH still works

The physical host owns the virtual switch too. So it can reach both VMs:

```bash
ssh snd@192.168.150.10
ssh recv@192.168.150.20
```

The VMs cannot use this network to reach the Internet. That is what makes it
appropriate for this lab.

## One network card, one address

Each VM has one network card: `ens3`. It should have one address:

```text
sender:   192.168.150.10/24
receiver: 192.168.150.20/24
```

Check it inside either VM:

```bash
ip -brief address
ip route
```

The route output should not contain `default via`. No default route means the
VM has no ordinary path out of the lab.

## Why there used to be two addresses

The VM network configuration originally said `iface ens3 inet dhcp`. That
asked the private network's DHCP service for an automatic address. We also
manually added `.10` or `.20`, so one card held two addresses.

The configuration now uses a fixed address instead. The important part of
`/etc/network/interfaces` is:

```text
allow-hotplug ens3
iface ens3 inet static
    address 192.168.150.10
    netmask 255.255.255.0
```

The receiver uses `.20` instead. There is deliberately no `gateway` line.

## Before any sender experiment

From the host, confirm that the VMs still have one private network card:

```bash
virsh -c qemu:///system domiflist syn-sender
virsh -c qemu:///system domiflist syn-receiver
```

Each output should show `syn-lab-isolated`, not `default`.

From sender, confirm the receiver is reachable:

```bash
ping -c 3 192.168.150.20
curl -I http://192.168.150.20
```
