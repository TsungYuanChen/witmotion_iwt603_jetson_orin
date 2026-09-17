# IWT603 dashboard installation

For Ubuntu/Debian Linux, including Jetson Orin with Ubuntu-based JetPack.
Requires administrator access, internet access, and kernel headers matching
the running kernel. Close applications using CH340/CH341 adapters and unplug
the adapters before installing.

Keep `install_iwt603.sh` and `iwt603_dashboard_curses.py` together, then run:

```sh
sh install_iwt603.sh
```

The installer requests sudo access and:
- Installs Python, pyserial, Git, build tools, and compression tools.
- Uses existing kernel headers, or attempts to install
  `nvidia-l4t-kernel-headers` on Jetson and matching Ubuntu/Debian headers elsewhere.
- Clones [WCH's driver](https://github.com/WCHSoftGroup/ch341ser_linux)
  into a unique directory under `/usr/local/src`, prints its commit, and runs
  `make clean`, `make`, and `make install` inside its `driver` directory.
- Installs a preferred module copy under `/lib/modules/$(uname -r)/updates`,
  runs `depmod`, and reloads `ch341` with `modprobe`.
- Configures loading at boot in `/etc/modules-load.d/iwt603-ch341.conf`.
- Grants `dialout` access to the WCH serial devices through a udev rule and adds
  the intended user to that group.
- Installs the dashboard under `/usr/local/lib/iwt603` and the launcher at
  `/usr/local/bin/iwt603-dashboard`.

From a root shell, use `sh install_iwt603.sh --user alice`, replacing alice
with the intended user. Re-running rebuilds the driver and updates the dashboard.

Log out completely and back in, reconnect the sensor, and run:

```sh
iwt603-dashboard
```

The WCH driver creates `/dev/ttyCH341USB0` (and numbered devices for additional
adapters). The dashboard detects the device automatically. To choose explicitly:

```sh
iwt603-dashboard --port /dev/ttyCH341USB0 --baud 921600
```

Press q or Ctrl+C to quit. The baud must match the sensor configuration.
The dashboard does not configure the sensor output rate.

Jetson headers must match the running L4T kernel exactly. If the installer
reports missing or mismatched headers, install the matching NVIDIA headers,
or reboot if a newer kernel was installed, then rerun. The script cannot
replace a driver compiled directly into the kernel. Kernel-enforced module
signing also requires signing the driver before it can load.

This source installation is specific to the running kernel, without DKMS.
Rerun the installer after kernel upgrades. It replaces the distribution's
CH341 module through the upstream install target and an updates-directory copy.
Each run retains its source checkout for diagnosis.

For connection failures, check `id -nG` for dialout membership and inspect
`sudo dmesg`. To check loading:

```sh
lsmod | grep ch341
modinfo -n ch341
ls /dev/ttyCH341USB*
```
