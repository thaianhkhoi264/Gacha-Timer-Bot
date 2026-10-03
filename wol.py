"""Wake-on-LAN helper (no external dependencies)."""
import re
import socket


def send_magic_packet(mac: str, broadcast_ip: str, port: int = 9) -> None:
    """Broadcast a Wake-on-LAN magic packet (6x 0xFF + 16x the MAC) over UDP."""
    hex_mac = re.sub(r"[^0-9A-Fa-f]", "", mac)
    if len(hex_mac) != 12:
        raise ValueError(f"Invalid MAC address: {mac!r}")
    packet = b"\xff" * 6 + bytes.fromhex(hex_mac) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast_ip, port))
