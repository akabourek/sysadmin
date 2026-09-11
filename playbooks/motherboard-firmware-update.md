# Motherboard firmware update (BIOS/UEFI)

**When to use:** the firmware is demonstrably the cause of a problem (device
initialization failures, ACPI AML errors, broken S3), the board is running its
launch firmware version, or a microcode security fix has been released.

**Risk:** **high.** A failed flash bricks the board. A successful flash usually
**resets all settings to their defaults** — and that breaks everything that
depended on a deviation from the defaults. In practice, the latter causes
trouble more often than the flash itself.

---

## 1. Diagnostics

### 1a. What is there now

- [ ] Firmware version and date, board model:
      `cat /sys/class/dmi/id/{bios_vendor,bios_version,bios_date,board_name}`
- [ ] Can it go the distribution's way? `fwupdmgr get-devices`, `fwupdmgr get-upgrades`.
      If the board publishes to LVFS, `fwupd` is clearly the preferred path —
      it is transactional and needs no USB drive. The existence of
      `/sys/firmware/efi/esrt/` **does not mean** there is an update on LVFS;
      consumer boards mostly do not publish there, and `fwupd` reports the
      placeholder version `1` for them.
- [ ] Boot order, so you can restore it: `efibootmgr`
- [ ] Prove that the firmware really is the cause. Do not enter this playbook
      on a guess — the journal should show a concrete failure (see the
      `system-check` skill).

### 1b. What depends on the firmware — go through **everything**

This is the core of the preparation. For every item, answer what happens when
the setting returns to its default.

| What to check | With | Why it hurts |
|---|---|---|
| Disk encryption | `cat /etc/crypttab`, `lsblk -o NAME,FSTYPE` | When LUKS is unlocked by the **TPM**, the flash changes the PCRs and the unlock stops matching. **Have the recovery key at hand, or you will not get to your data.** |
| Secure Boot | `mokutil --sb-state` | When it is currently **disabled** and you have unsigned out-of-tree kernel modules (graphics, VirtualBox), Secure Boot switched on after the flash will silence them. |
| Fallback display | `/proc/cmdline`, `/sys/class/drm/*/status` | The combination "blacklisted free driver + non-working proprietary driver + disabled integrated graphics" = **a black screen with no way back**. |
| Memory profile | XMP / EXPO / A-XMP in the BIOS | After a reset the memory runs at JEDEC speed. Nothing breaks, it just gets slower. |
| Resizable BAR | `lspci -v -s <dGPU>` — the prefetchable BAR size matches the VRAM | A reset drops graphics performance. |
| Virtualization | `/sys/class/iommu/`, `svm`/`vmx` in `/proc/cpuinfo` | Disabled SVM/IOMMU breaks KVM, libvirt and device passthrough. |
| Another OS on the disk | `lsblk -f`, `efibootmgr` | Windows with BitLocker asks for its recovery key after a firmware change. |

### 1c. Target version

- [ ] Find the release notes of **all** versions between the current and the
      target one, not just the latest. Look for an entry that matches your
      problem.
- [ ] Find out whether any of them says "cannot be downgraded".
      On AMD platforms this is common, and it is irreversible.
- [ ] Do not skip intermediate versions if the vendor states they must be
      installed in order.

---

## 2. Backup

Firmware cannot be backed up. What you back up is **the state around it**.

- [ ] **Photograph or write down every BIOS settings page** where something
      differs from the default. After the flash, that will be the only record
      of what was there.
- [ ] Save the `efibootmgr` output into a report for the machine.
- [ ] Keep the recovery keys for encrypted volumes **physically off this
      machine**. They do not belong in the repository.
- [ ] Prepare **rescue media** (a live USB of the same distribution).
- [ ] Find out whether the board has an emergency flash without CPU and RAM
      (vendors call it BIOS Flashback / Flash BIOS Button / Q-Flash Plus).
      That is your way back if the flash fails — and it uses **a different
      file name** than the regular path. Find out in advance, not in an
      emergency.

---

## 3. Intervention

### 3a. Preferred path: `fwupd`

When the update is on LVFS, everything is done from the running system:

```
fwupdmgr refresh
fwupdmgr get-upgrades
fwupdmgr upgrade <device-id>
```

The update is applied on the next reboot. It needs neither a USB drive nor
manual file naming.

### 3b. Fallback path: the vendor's tool in the BIOS

When the board is not on LVFS:

| Vendor | BIOS tool | File note |
|---|---|---|
| MSI | M-FLASH | Original name from the zip. For Flash BIOS Button, rename to `MSI.ROM`. |
| ASUS | EZ Flash | Some models require renaming, see the manual. |
| Gigabyte | Q-Flash | For Q-Flash Plus, rename to `GIGABYTE.bin`. |
| ASRock | Instant Flash | Original name. |

The procedure is the same for all of them:

1. Format the USB drive as **FAT32** and extract the file into its root.
2. Reboot into the BIOS, start the vendor's tool, select the file.
3. **Do not interrupt.** The board reboots several times on its own. Do not
   power off, do not pull the USB drive, do not press reset.

### 3c. The step people forget

**After the flash, stay in the BIOS and go through the settings from 1b before
you boot into the system for the first time.** This is not about convenience —
with the combination "unsigned modules + Secure Boot enabled + no fallback
graphics output" you cannot fix the settings from the booted system, because
you will not see anything on the screen.

---

## 4. Verifying the result

- [ ] `cat /sys/class/dmi/id/bios_version /sys/class/dmi/id/bios_date` — the new version is there
- [ ] `mokutil --sb-state` — matches what you set
- [ ] `lsmod | grep <critical module>` — the out-of-tree modules loaded
- [ ] `efibootmgr` — the boot order matches the record from step 2
- [ ] `journalctl -b -p warning` — the original error is gone and **no new one appeared**
- [ ] Repeat the **concrete test of the problem** you flashed for.
      Once is not enough when the problem was intermittent — run enough cycles
      that the original frequency of occurrence is demonstrably exceeded.

---

## 5. Rollback

**Only partially reversible.** You restore the BIOS settings by hand from
step 2, but the firmware itself often **cannot be flashed back** — vendors and
platforms enforce downgrade protection. That has to be accounted for **before**
the flash, not after it.

When the flash fails and the board does not start: the emergency flash without
CPU and RAM from step 2.

---

## 6. Record

- `hosts/<hostname>/facts.md` — the new firmware version and date.
- `hosts/<hostname>/NOTES.md` — why it was flashed, to which version, what had
  to be restored after the reset, and whether it solved the original problem.
  Record the **non-default settings** separately — you will need them again at
  the next flash.
