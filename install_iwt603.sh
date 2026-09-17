#!/bin/sh
# Ubuntu/Debian and Jetson installer using the WCH source driver. Keep beside iwt603_dashboard_curses.py.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
case "${1:-}" in
    -h|--help)
        printf 'Usage: sh install_iwt603.sh [--user USER]\nBuilds the WCH CH340/CH341 driver and installs iwt603-dashboard on Ubuntu/Debian and Jetson.\n'
        exit 0 ;;
esac
target_user=${SUDO_USER:-$(id -un)}
if [ "$#" -gt 0 ]; then
    [ "$#" -eq 2 ] && [ "$1" = --user ] || fail 'Use --help for usage.'
    target_user=$2
fi
id "$target_user" >/dev/null 2>&1 || fail "Unknown user: $target_user"
[ "$(uname -s)" = Linux ] || fail 'This installer supports Linux only.'
[ -r /etc/os-release ] || fail 'Cannot identify Linux distribution.'
. /etc/os-release
case " ${ID:-} ${ID_LIKE:-} " in
    *' debian '*|*' ubuntu '*) ;;
    *) fail 'This installer supports Ubuntu/Debian and derivatives.' ;;
esac
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_file=$script_dir/iwt603_dashboard_curses.py
[ -f "$source_file" ] || fail "Missing $source_file; keep both files together."
if [ "$(id -u)" -ne 0 ]; then
    command -v sudo >/dev/null 2>&1 || fail 'Run as root with --user USER, or install sudo.'
    exec sudo sh "$script_dir/install_iwt603.sh" --user "$target_user"
fi
[ "$target_user" != root ] || fail 'Specify --user USER to grant a regular user serial access.'

apt-get update
apt-get install -y python3 python3-serial kmod git ca-certificates build-essential xz-utils zstd

kernel_release=$(uname -r)
kernel_build=/lib/modules/$kernel_release/build
if [ ! -f "$kernel_build/Makefile" ]; then
    case "$kernel_release" in
        *tegra*)
            apt-get install -y nvidia-l4t-kernel-headers ||
                fail 'Install NVIDIA kernel headers matching your JetPack/L4T release and rerun.' ;;
        *)
            apt-get install -y "linux-headers-$kernel_release" ||
                fail "Install kernel headers matching $kernel_release and rerun." ;;
    esac
fi
[ -f "$kernel_build/Makefile" ] ||
    fail "Missing $kernel_build/Makefile. Install headers for the running kernel; reboot first if your kernel was updated."
header_release=$(make -s -C "$kernel_build" kernelrelease)
[ "$header_release" = "$kernel_release" ] ||
    fail "Headers are for $header_release, but running kernel is $kernel_release. Install matching headers or reboot into the matching kernel."

# A built-in driver cannot be replaced by an external module.
if [ -d /sys/module/ch341 ] && ! grep -q '^ch341 ' /proc/modules; then
    fail 'ch341 is built into this kernel. Use a kernel with CH341 configured as a module to install the WCH replacement.'
fi

# Keep each source checkout for diagnostics and record exactly what was built.
install -d -m 0755 /usr/local/src
driver_source=$(mktemp -d /usr/local/src/iwt603-ch341.XXXXXX)
git clone --depth 1 https://github.com/WCHSoftGroup/ch341ser_linux.git "$driver_source"
printf 'WCH source: %s\nCommit: ' "$driver_source"
git -C "$driver_source" rev-parse HEAD
(
    cd "$driver_source/driver"
    make clean
    make
    # Stop applications using CH340/CH341 ports before replacing the driver.
    if grep -q '^ch341 ' /proc/modules; then
        modprobe -r ch341 ||
            fail 'Close applications using CH340/CH341 ports, unplug the adapters, and rerun.'
    fi
    make install
    # Upstream ignores some install failures. Install a verified preferred copy.
    install -d -m 0755 "/lib/modules/$kernel_release/updates"
    install -m 0644 ch341.ko "/lib/modules/$kernel_release/updates/ch341.ko"
)
depmod -a "$kernel_release"
[ "$(modinfo -n ch341)" = "/lib/modules/$kernel_release/updates/ch341.ko" ] ||
    fail 'modprobe is selecting another ch341 module. Check depmod configuration.'
# make install attempts insmod itself; reload the installed copy explicitly.
if grep -q '^ch341 ' /proc/modules; then
    modprobe -r ch341 ||
        fail 'Driver installed but cannot reload. Close serial applications, unplug adapters, and rerun.'
fi
modprobe ch341 ||
    fail 'Driver installed but cannot load. Check sudo dmesg for kernel/header mismatch or module signing requirements.'

getent group dialout >/dev/null || groupadd --system dialout
install -d -m 0755 /etc/modules-load.d /etc/udev/rules.d
printf 'ch341\n' > /etc/modules-load.d/iwt603-ch341.conf
printf 'SUBSYSTEM=="tty", KERNEL=="ttyCH341USB*", GROUP="dialout", MODE="0660"\n' > /etc/udev/rules.d/99-iwt603-ch341.rules
if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules
    udevadm trigger --subsystem-match=tty --sysname-match='ttyCH341USB*'
fi

/usr/bin/python3 -c 'import curses, serial; from serial.tools import list_ports'
usermod -a -G dialout "$target_user"
install -d -m 0755 /usr/local/lib/iwt603 /usr/local/bin
install -m 0644 "$source_file" /usr/local/lib/iwt603/iwt603_dashboard_curses.py
launcher=$(mktemp)
trap 'rm -f "$launcher"' 0
trap 'exit 1' HUP INT TERM
cat > "$launcher" <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /usr/local/lib/iwt603/iwt603_dashboard_curses.py "$@"
EOF
install -m 0755 "$launcher" /usr/local/bin/iwt603-dashboard
printf '\nInstalled iwt603-dashboard for %s.\nLog out and back in to activate serial permissions, then connect the sensor and run:\n  iwt603-dashboard\nOr select a device explicitly:\n  iwt603-dashboard --port /dev/ttyCH341USB0\n' "$target_user"
