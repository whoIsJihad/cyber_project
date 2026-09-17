#!/usr/bin/env bash

# Prepare the two powered-off Debian installer VMs for the SYN lab.
# Run this script on the physical Ubuntu host, not inside a VM.

set -Eeuo pipefail

readonly LIBVIRT_URI="qemu:///system"
readonly ISO_BASE_URL="https://cdimage.debian.org/debian-cd/current/amd64/iso-cd"
readonly LOCAL_ISO="/home/jihad/ISOs/debian-13.7.0-amd64-netinst.iso"
readonly IMAGE_POOL="images"
readonly LAB_NETWORK="syn-lab-isolated"
readonly LAB_BRIDGE_ADDRESS="192.168.150.1"
readonly LAB_NETMASK="255.255.255.0"
readonly LAB_DHCP_START="192.168.150.100"
readonly LAB_DHCP_END="192.168.150.199"
readonly VM_MEMORY_MIB="512"
readonly VM_VCPUS="1"
readonly VM_DISK_GIB="6"
readonly -a VM_NAMES=("syn-sender" "syn-receiver")

temporary_directory=""

cleanup() {
  if [[ -n "${temporary_directory}" && -d "${temporary_directory}" ]]; then
    rm -rf -- "${temporary_directory}"
  fi
}
trap cleanup EXIT

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

heading() {
  printf '\n==> %s\n' "$*"
}

for required_command in curl awk sha512sum stat virsh virt-install; do
  command -v "${required_command}" >/dev/null 2>&1 ||
    die "Missing command: ${required_command}"
done

[[ -c /dev/kvm ]] || die "/dev/kvm does not exist; KVM is not available."

heading "Checking the system libvirt connection"
virsh -c "${LIBVIRT_URI}" version >/dev/null

if ! virsh -c "${LIBVIRT_URI}" pool-info "${IMAGE_POOL}" >/dev/null 2>&1; then
  heading "Creating the standard libvirt storage pool"
  virsh -c "${LIBVIRT_URI}" pool-define-as \
    --name "${IMAGE_POOL}" \
    --type dir \
    --target /var/lib/libvirt/images >/dev/null
  virsh -c "${LIBVIRT_URI}" pool-autostart "${IMAGE_POOL}" >/dev/null
fi

pool_state="$(virsh -c "${LIBVIRT_URI}" pool-info "${IMAGE_POOL}" | awk '/^State:/ {print $2}')"
if [[ "${pool_state}" != "running" ]]; then
  virsh -c "${LIBVIRT_URI}" pool-start "${IMAGE_POOL}"
fi

virsh -c "${LIBVIRT_URI}" net-info default >/dev/null 2>&1 ||
  die "The libvirt NAT network named 'default' does not exist."

default_network_active="$(virsh -c "${LIBVIRT_URI}" net-info default | awk '/^Active:/ {print $2}')"
if [[ "${default_network_active}" != "yes" ]]; then
  virsh -c "${LIBVIRT_URI}" net-start default
fi

# Refuse ambiguous partial setups instead of overwriting disks or definitions.
for vm_name in "${VM_NAMES[@]}"; do
  if virsh -c "${LIBVIRT_URI}" dominfo "${vm_name}" >/dev/null 2>&1; then
    die "VM '${vm_name}' already exists. Nothing was overwritten."
  fi

  if virsh -c "${LIBVIRT_URI}" vol-info --pool "${IMAGE_POOL}" "${vm_name}.qcow2" >/dev/null 2>&1; then
    die "Disk '${vm_name}.qcow2' already exists without a matching VM. Nothing was overwritten."
  fi
done

temporary_directory="$(mktemp -d)"

heading "Finding the current official Debian stable amd64 netinst ISO"
checksums_file="${temporary_directory}/SHA512SUMS"
curl --fail --location --proto '=https' --tlsv1.2 \
  --output "${checksums_file}" "${ISO_BASE_URL}/SHA512SUMS"

iso_filename="$(awk '$2 ~ /^debian-[0-9.]+-amd64-netinst\.iso$/ {print $2; exit}' "${checksums_file}")"
[[ -n "${iso_filename}" ]] || die "Could not find the Debian amd64 netinst filename in SHA512SUMS."

[[ -f "${LOCAL_ISO}" ]] || die "The downloaded ISO was not found at '${LOCAL_ISO}'."
[[ "$(basename "${LOCAL_ISO}")" == "${iso_filename}" ]] ||
  die "The local ISO is not the current Debian stable netinst image listed by Debian."

heading "Verifying the ISO SHA-512 checksum"
expected_checksum="$(awk -v wanted="${iso_filename}" '$2 == wanted {print $1; exit}' "${checksums_file}")"
actual_checksum="$(sha512sum "${LOCAL_ISO}" | awk '{print $1}')"

if [[ "${actual_checksum}" != "${expected_checksum}" ]]; then
  die "ISO checksum mismatch. Delete '${LOCAL_ISO}' and download it again."
fi
printf 'Checksum verified: %s\n' "${iso_filename}"

# Upload through libvirt so QEMU can read the ISO even though the user's home
# directory is intentionally not accessible to the libvirt service account.
if virsh -c "${LIBVIRT_URI}" vol-info --pool "${IMAGE_POOL}" "${iso_filename}" >/dev/null 2>&1; then
  iso_capacity="$(virsh -c "${LIBVIRT_URI}" vol-info --pool "${IMAGE_POOL}" "${iso_filename}" --bytes | awk '/^Capacity:/ {print $2}')"
  local_iso_size="$(stat -c '%s' "${LOCAL_ISO}")"
  [[ "${iso_capacity}" == "${local_iso_size}" ]] ||
    die "An ISO volume with the same name but a different size already exists in libvirt storage."
else
  heading "Uploading the verified ISO into libvirt storage"
  local_iso_size="$(stat -c '%s' "${LOCAL_ISO}")"
  virsh -c "${LIBVIRT_URI}" vol-create-as \
    --pool "${IMAGE_POOL}" \
    --name "${iso_filename}" \
    --capacity "${local_iso_size}" \
    --format raw >/dev/null
  virsh -c "${LIBVIRT_URI}" vol-upload \
    --pool "${IMAGE_POOL}" \
    --vol "${iso_filename}" \
    --file "${LOCAL_ISO}"
fi
iso_path="$(virsh -c "${LIBVIRT_URI}" vol-path --pool "${IMAGE_POOL}" "${iso_filename}")"

if virsh -c "${LIBVIRT_URI}" net-info "${LAB_NETWORK}" >/dev/null 2>&1; then
  heading "Checking the existing ${LAB_NETWORK} network"
  network_xml="$(virsh -c "${LIBVIRT_URI}" net-dumpxml "${LAB_NETWORK}")"

  if grep -q '<forward' <<<"${network_xml}"; then
    die "Existing network '${LAB_NETWORK}' contains forwarding and is not safe for this lab."
  fi

  if ! grep -q "address='${LAB_BRIDGE_ADDRESS}'" <<<"${network_xml}"; then
    die "Existing network '${LAB_NETWORK}' uses an unexpected address. Inspect it manually."
  fi
else
  heading "Creating the isolated ${LAB_NETWORK} network"
  network_definition="${temporary_directory}/${LAB_NETWORK}.xml"
  cat >"${network_definition}" <<NETWORK_XML
<network>
  <name>${LAB_NETWORK}</name>
  <bridge name='virbr150' stp='on' delay='0'/>
  <ip address='${LAB_BRIDGE_ADDRESS}' netmask='${LAB_NETMASK}'>
    <dhcp>
      <range start='${LAB_DHCP_START}' end='${LAB_DHCP_END}'/>
    </dhcp>
  </ip>
</network>
NETWORK_XML

  # No <forward> element means libvirt does not route this network outward.
  virsh -c "${LIBVIRT_URI}" net-define "${network_definition}" >/dev/null
  virsh -c "${LIBVIRT_URI}" net-autostart "${LAB_NETWORK}" >/dev/null
fi

lab_network_active="$(virsh -c "${LIBVIRT_URI}" net-info "${LAB_NETWORK}" | awk '/^Active:/ {print $2}')"
if [[ "${lab_network_active}" != "yes" ]]; then
  virsh -c "${LIBVIRT_URI}" net-start "${LAB_NETWORK}" >/dev/null
fi

heading "Creating powered-off VM definitions"
for vm_name in "${VM_NAMES[@]}"; do
  volume_name="${vm_name}.qcow2"
  virsh -c "${LIBVIRT_URI}" vol-create-as \
    --pool "${IMAGE_POOL}" \
    --name "${volume_name}" \
    --capacity "${VM_DISK_GIB}G" \
    --format qcow2 >/dev/null

  disk_path="$(virsh -c "${LIBVIRT_URI}" vol-path --pool "${IMAGE_POOL}" "${volume_name}")"
  domain_definition="${temporary_directory}/${vm_name}.xml"

  virt-install \
    --connect "${LIBVIRT_URI}" \
    --name "${vm_name}" \
    --description "Debian VM for the isolated university SYN lab" \
    --memory "${VM_MEMORY_MIB}" \
    --vcpus "${VM_VCPUS}" \
    --cpu host-model \
    --disk "path=${disk_path},format=qcow2,bus=virtio" \
    --cdrom "${iso_path}" \
    --network "network=default,model=virtio" \
    --graphics spice \
    --video virtio \
    --osinfo "detect=on,require=off" \
    --boot "cdrom,hd,menu=on" \
    --noautoconsole \
    --print-xml 1 >"${domain_definition}"

  virsh -c "${LIBVIRT_URI}" define "${domain_definition}" >/dev/null
  printf 'Defined %-14s  %s MiB RAM, %s vCPU, %s GiB disk\n' \
    "${vm_name}" "${VM_MEMORY_MIB}" "${VM_VCPUS}" "${VM_DISK_GIB}"
done

heading "Final verification"
virsh -c "${LIBVIRT_URI}" list --all
printf '\n'
virsh -c "${LIBVIRT_URI}" net-list --all

cat <<FINAL_MESSAGE

Setup finished successfully.

The VMs are defined but powered off:
  - syn-sender
  - syn-receiver

They currently use the 'default' NAT network so the Debian netinst installer
can download packages. Open virt-manager, connect to QEMU/KVM System, and start
one VM at a time. Complete the Debian installation choices in
VM_LAB_SETUP_GUIDE.md.

Before any crafted-packet experiment, power both VMs off and replace their
'default' NIC source with '${LAB_NETWORK}'. Never leave NAT attached during an
experiment.
FINAL_MESSAGE
