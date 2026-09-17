#!/usr/bin/env python3

import argparse
import glob
import curses
import locale
import math
import serial
import struct
import time
from serial.tools import list_ports

PORT = "/dev/ttyCH341USB0"
BAUD = 921600

REQUESTED_SENSOR_HZ = 1000
DISPLAY_HZ = 20.0

G = 9.80665

# WIT packet IDs
ACC_ID   = 0x51
GYRO_ID  = 0x52
ANGLE_ID = 0x53
MAG_ID   = 0x54
QUAT_ID  = 0x59

VALID_PACKET_IDS = {
    ACC_ID,
    GYRO_ID,
    ANGLE_ID,
    MAG_ID,
    QUAT_ID,
}


def int16(lo, hi):
    return struct.unpack("<h", bytes([lo, hi]))[0]


def checksum_ok(packet):
    return (sum(packet[:10]) & 0xFF) == packet[10]


def decode(packet):
    packet_type = packet[1]

    if packet_type == ACC_ID:
        ax = int16(packet[2], packet[3]) / 32768.0 * 16.0 * G
        ay = int16(packet[4], packet[5]) / 32768.0 * 16.0 * G
        az = int16(packet[6], packet[7]) / 32768.0 * 16.0 * G
        temp = int16(packet[8], packet[9]) / 100.0

        return packet_type, {
            "ax": ax,
            "ay": ay,
            "az": az,
            "temp": temp,
        }

    if packet_type == GYRO_ID:
        gx = int16(packet[2], packet[3]) / 32768.0 * 2000.0
        gy = int16(packet[4], packet[5]) / 32768.0 * 2000.0
        gz = int16(packet[6], packet[7]) / 32768.0 * 2000.0

        return packet_type, {
            "gx": gx,
            "gy": gy,
            "gz": gz,
        }

    if packet_type == ANGLE_ID:
        roll = int16(packet[2], packet[3]) / 32768.0 * 180.0
        pitch = int16(packet[4], packet[5]) / 32768.0 * 180.0
        yaw = int16(packet[6], packet[7]) / 32768.0 * 180.0

        return packet_type, {
            "roll": roll,
            "pitch": pitch,
            "yaw": yaw,
        }

    if packet_type == MAG_ID:
        mx = int16(packet[2], packet[3])
        my = int16(packet[4], packet[5])
        mz = int16(packet[6], packet[7])

        return packet_type, {
            "mx": mx,
            "my": my,
            "mz": mz,
        }

    if packet_type == QUAT_ID:
        # WIT quaternion packet 0x59:
        # Q0(W), Q1(X), Q2(Y), Q3(Z)
        qw = int16(packet[2], packet[3]) / 32768.0
        qx = int16(packet[4], packet[5]) / 32768.0
        qy = int16(packet[6], packet[7]) / 32768.0
        qz = int16(packet[8], packet[9]) / 32768.0

        return packet_type, {
            "qw": qw,
            "qx": qx,
            "qy": qy,
            "qz": qz,
        }

    return None, None


def v(data, key):
    if data is None:
        return 0.0
    return data.get(key, 0.0)


def dashboard_lines(latest, rates):
    acc = latest.get(ACC_ID)
    gyro = latest.get(GYRO_ID)
    angle = latest.get(ANGLE_ID)
    quat = latest.get(QUAT_ID)

    ax = v(acc, "ax")
    ay = v(acc, "ay")
    az = v(acc, "az")
    temp = v(acc, "temp")

    gx = v(gyro, "gx")
    gy = v(gyro, "gy")
    gz = v(gyro, "gz")

    gx_rad = math.radians(gx)
    gy_rad = math.radians(gy)
    gz_rad = math.radians(gz)

    roll = v(angle, "roll")
    pitch = v(angle, "pitch")
    yaw = v(angle, "yaw")

    qw = v(quat, "qw")
    qx = v(quat, "qx")
    qy = v(quat, "qy")
    qz = v(quat, "qz")

    return [
        "========== IWT603 ==========",
        f"Port                  : {PORT}",
        f"Baud                  : {BAUD}",
        f"Requested sensor rate : {REQUESTED_SENSOR_HZ} Hz",
        "",
        "Measured packet rates :",
        (
            f"  ACC   {rates[ACC_ID]:7.1f} Hz | "
            f"GYRO  {rates[GYRO_ID]:7.1f} Hz | "
            f"ANGLE {rates[ANGLE_ID]:7.1f} Hz | "
            f"QUAT  {rates[QUAT_ID]:7.1f} Hz"
        ),
        f"Display refresh       : {DISPLAY_HZ:g} Hz",
        "",
        "Acceleration [m/s²]",
        f"  X: {ax:9.4f}  Y: {ay:9.4f}  Z: {az:9.4f}",
        f"Temperature: {temp:.2f} °C",
        "",
        "Gyroscope [deg/s]",
        f"  X: {gx:9.4f}  Y: {gy:9.4f}  Z: {gz:9.4f}",
        "",
        "Gyroscope [rad/s]",
        f"  X: {gx_rad:9.4f}  Y: {gy_rad:9.4f}  Z: {gz_rad:9.4f}",
        "",
        "Euler angle [deg]",
        f"  Roll : {roll:9.3f}  Pitch: {pitch:9.3f}  Yaw  : {yaw:9.3f}",
        "",
        "Quaternion [W, X, Y, Z]",
        f"  W: {qw:9.5f}  X: {qx:9.5f}  Y: {qy:9.5f}  Z: {qz:9.5f}",
        "",
        "Press Ctrl+C to stop",
    ]


def draw_dashboard(stdscr, latest, rates):
    stdscr.erase()

    max_y, max_x = stdscr.getmaxyx()
    lines = dashboard_lines(latest, rates)

    for row, line in enumerate(lines):
        if row >= max_y - 1:
            break

        # Avoid curses errors when terminal is narrower than the text.
        try:
            stdscr.addnstr(row, 0, line, max(0, max_x - 1))
        except curses.error:
            pass

    stdscr.refresh()


def run(stdscr):
    # Terminal configuration
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)

    ser = serial.Serial(
        port=PORT,
        baudrate=BAUD,
        timeout=0.001,
    )

    ser.reset_input_buffer()

    buffer = bytearray()
    latest = {}

    counts = {
        ACC_ID: 0,
        GYRO_ID: 0,
        ANGLE_ID: 0,
        MAG_ID: 0,
        QUAT_ID: 0,
    }

    rates = {
        ACC_ID: 0.0,
        GYRO_ID: 0.0,
        ANGLE_ID: 0.0,
        MAG_ID: 0.0,
        QUAT_ID: 0.0,
    }

    rate_start = time.perf_counter()
    display_period = 1.0 / DISPLAY_HZ
    next_display = time.perf_counter()

    try:
        while True:
            # Read all currently available bytes.
            waiting = ser.in_waiting
            data = ser.read(waiting if waiting > 0 else 1)

            if data:
                buffer.extend(data)

            # Decode all complete 11-byte packets.
            while len(buffer) >= 11:
                if buffer[0] != 0x55:
                    del buffer[0]
                    continue

                if buffer[1] not in VALID_PACKET_IDS:
                    del buffer[0]
                    continue

                packet = buffer[:11]

                if not checksum_ok(packet):
                    del buffer[0]
                    continue

                del buffer[:11]

                packet_type, values = decode(packet)

                if packet_type is not None:
                    latest[packet_type] = values
                    counts[packet_type] += 1

            now = time.perf_counter()

            # Calculate independent packet rates once per second.
            elapsed = now - rate_start
            if elapsed >= 1.0:
                for packet_type in rates:
                    rates[packet_type] = counts[packet_type] / elapsed
                    counts[packet_type] = 0

                rate_start = now

            # Fixed-screen refresh at 20 Hz.
            if now >= next_display:
                draw_dashboard(stdscr, latest, rates)
                next_display = now + display_period

            # Optional keyboard quit: q
            try:
                key = stdscr.getch()
                if key in (ord("q"), ord("Q")):
                    break
            except curses.error:
                pass

    finally:
        ser.close()


def main():
    global PORT, BAUD
    parser = argparse.ArgumentParser(description="Live IWT603 serial dashboard")
    parser.add_argument("--port", help="Serial device, e.g. /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=BAUD, help="Baud rate (default: 921600)")
    args = parser.parse_args()
    if args.baud <= 0:
        parser.error("--baud must be positive")
    if args.port:
        PORT = args.port
    else:
        candidates = sorted(set(glob.glob("/dev/ttyCH341USB*")) | {
            port.device for port in list_ports.comports()
            if (port.vid, port.pid) in {(0x1A86, 0x7523), (0x1A86, 0x5523)}
        })
        if not candidates:
            parser.error("No CH340/CH341 found. Connect the sensor or specify --port /dev/ttyUSB0")
        if len(candidates) > 1:
            parser.error("Multiple adapters found; choose --port from: " + ", ".join(candidates))
        PORT = candidates[0]
    BAUD = args.baud
    # Let curses handle UTF-8 symbols such as ² and °.
    locale.setlocale(locale.LC_ALL, "")

    try:
        curses.wrapper(run)
    except KeyboardInterrupt:
        pass
    except serial.SerialException as exc:
        parser.exit(1, f"Cannot use {PORT}: {exc}\nCheck the cable, --port, and dialout membership; log out and back in after installation.\n")

    print("Stopping IWT603 reader...")


if __name__ == "__main__":
    main()
