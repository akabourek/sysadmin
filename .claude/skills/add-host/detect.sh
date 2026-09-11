# Detection set for a new machine (CLAUDE.md §4). Read-only, no root, writes nothing.
# Run on the machine itself, after approval:
#   mkdir -p tmp && bash .claude/skills/add-host/detect.sh > tmp/detect.txt 2>&1
# The output contains the machine-id, addresses and a list of services. It does not belong in a commit (tmp/ is in .gitignore).
# A missing tool is printed as "(x missing)", so "not there" can be told apart from "found nothing".
export LC_ALL=C
s() { printf '\n===== %s\n' "$*"; }
has() { command -v "$1" >/dev/null 2>&1; }
need() { has "$1" || { echo "($1 missing)"; return 1; }; }
unit() { for u in "$@"; do printf '%s: %s / %s\n' "$u" "$(systemctl is-active "$u" 2>&1)" "$(systemctl is-enabled "$u" 2>&1)"; done; }

s hostname;               hostname; hostnamectl 2>&1
s os-release;             cat /etc/os-release
s kernel;                 uname -r -m
s machine-id;             cat /etc/machine-id
s uptime;                 uptime
s time;                   timedatectl 2>&1 | grep -E 'Time zone|NTP|synchronized'

s dmi
for f in chassis_type sys_vendor product_name product_version board_vendor board_name bios_vendor bios_version bios_date; do
  printf '%s: %s\n' "$f" "$(cat /sys/class/dmi/id/$f 2>/dev/null)"
done
s device-tree-model;      { tr -d '\0' < /proc/device-tree/model; } 2>/dev/null || echo "(none, typically x86)"
s cpu;                    lscpu | grep -E 'Model name|^CPU\(s\)|Thread|Core|Socket|Architecture|Virtualization'
s memory;                 free -h
s pci;                    need lspci && lspci | grep -iE 'vga|3d|display|ethernet|network|nvme|sata|raid'
s disks;                  lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,ROTA
s df;                     df -hT -x tmpfs -x devtmpfs -x efivarfs -x squashfs -x overlay
s swap;                   swapon --show
s raid-mdstat;            cat /proc/mdstat 2>/dev/null || echo "(no mdraid)"
s zfs;                    need zpool && zpool list 2>&1
s firmware-mode;          [ -d /sys/firmware/efi ] && echo UEFI || echo BIOS/legacy
s bootloader;             ls -d /boot/efi/EFI/* /boot/grub* /boot/loader 2>/dev/null
s secure-boot;            need mokutil && mokutil --sb-state 2>&1
s virtualization;         systemd-detect-virt 2>&1

s init;                   ps -p 1 -o comm=
s default-target;         systemctl get-default
s display-manager;        unit display-manager
s desktop;                echo "XDG_CURRENT_DESKTOP=${XDG_CURRENT_DESKTOP:-} XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-} SSH_CONNECTION=${SSH_CONNECTION:+yes}"
s sessions;               loginctl list-sessions --no-legend 2>&1
s package-managers;       for b in dnf5 dnf apt pacman zypper rpm-ostree flatpak snap nix brew; do has $b && echo "$b: $(command -v $b)"; done
s package-count;          has rpm && echo "rpm: $(rpm -qa | wc -l)"; has dpkg && echo "dpkg: $(dpkg -l | grep -c '^ii')"
s repositories
[ -d /etc/yum.repos.d ] && grep -HE '^\[|^enabled' /etc/yum.repos.d/*.repo
[ -d /etc/apt ] && grep -rHE '^(deb |URIs|Suites|Components|Enabled)' /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null
s automatic-updates
systemctl list-timers --all --no-legend 2>/dev/null | grep -iE 'dnf|apt|unattended|packagekit|rpm-ostree|zypp|pacman'
has rpm && rpm -q dnf-automatic dnf5-plugin-automatic 2>&1
has dpkg && { dpkg -s unattended-upgrades 2>/dev/null | grep '^Status' || echo "unattended-upgrades: missing"; apt-config dump 2>/dev/null | grep -E 'Periodic::(Update-Package-Lists|Unattended-Upgrade)'; }
s containers-virt;        for b in podman docker virsh lxc incus toolbox distrobox; do has $b && echo "$b: $(command -v $b)"; done

s firewall;               unit firewalld ufw nftables netfilter-persistent; echo "(the rules themselves are not detectable without root)"
s lsm;                    cat /sys/kernel/security/lsm 2>/dev/null; echo; has getenforce && getenforce; cat /sys/module/apparmor/parameters/enabled 2>/dev/null

s net-interfaces;         ip -br a
s net-routes;             ip r
s dns;                    has resolvectl && resolvectl status 2>&1 | grep -E 'Link|Current DNS|DNS Servers|resolv.conf mode'; grep -v '^#' /etc/resolv.conf
s network-manager;        unit NetworkManager systemd-networkd networking
s listening-ports;        ss -tulnH
s sshd;                   unit sshd ssh sshd.socket ssh.socket
s avahi;                  unit avahi-daemon

s user;                   id; getent passwd "$(id -un)" | cut -d: -f7
s tools
for b in bash fish zsh git python3 tmux screen curl sudo; do printf '%s: %s\n' "$b" "$(command -v $b || echo missing)"; done
printf 'claude: %s\n' "$(command -v claude || ls ~/.local/bin/claude 2>/dev/null || echo missing)"
s services-enabled;       systemctl list-unit-files --state=enabled --type=service --no-legend
s services-failed;        systemctl --failed --no-legend
s logind;                 grep -hvE '^#|^$|^\[' /etc/systemd/logind.conf /etc/systemd/logind.conf.d/*.conf 2>/dev/null || echo "(defaults)"
