#!/usr/bin/env python3
"""Which names did the phone ask for, in a capture? Reads a PCAP file (PCAPdroid's pcap_file mode: raw IP packets) and
lists the names that travel in clear: the server name of each TLS connection (SNI), HTTP Host headers, DNS questions.
  python3 -I privacy/pcap_domains.py FILE.pcap [--json]
  python3 -I privacy/pcap_domains.py --selftest
What no capture shows, by design of the protocols, and what this prints instead:
- QUIC (UDP 443): the name is encrypted in the first packet; counted per address as "quic, name not readable";
- Encrypted Client Hello: the outer name only (the provider's), not the site;
- DNS with Private DNS on (this phone: AdGuard DNS over TLS): the questions travel inside TLS to the resolver, so the
  only DNS name in the capture is the resolver's own. Names then come from SNI and HTTP Host only.
No dependency: the file is read with struct. One app at a time gives per-app names (PCAPdroid's app_filter)."""
import collections, ipaddress, json, struct, sys

HTTP = (b"GET ", b"POST ", b"HEAD ", b"PUT ", b"DELETE ", b"OPTIONS ", b"PATCH ", b"CONNECT ")


def packets(data):
    """(ip packet bytes) of a classic pcap file, whatever its byte order; link types: raw IP, Ethernet, Linux cooked, loopback."""
    if len(data) < 24:
        raise ValueError("not a pcap file (too short)")
    magic = data[:4]
    order = {b"\xd4\xc3\xb2\xa1": "<", b"\xa1\xb2\xc3\xd4": ">", b"\x4d\x3c\xb2\xa1": "<", b"\xa1\xb2\x3c\x4d": ">"}.get(magic)
    if not order:
        raise ValueError("not a classic pcap file (PCAPNG is not read: use PCAPdroid's default pcap format)")
    link = struct.unpack(order + "I", data[20:24])[0]
    skip = {101: 0, 228: 0, 229: 0, 1: 14, 113: 16, 0: 4, 12: 0}.get(link)
    if skip is None:
        raise ValueError(f"link type {link} is not read")
    pos = 24
    while pos + 16 <= len(data):
        size = struct.unpack(order + "I", data[pos + 8:pos + 12])[0]
        frame = data[pos + 16:pos + 16 + size]
        pos += 16 + size
        if link == 1 and frame[12:14] == b"\x81\x00":  # one VLAN tag
            frame = frame[4:]
        yield frame[skip:]


def transport(ip):
    """(protocol, destination address, source port, destination port, payload) of an IPv4 or IPv6 packet, or None."""
    if len(ip) < 20:
        return None
    if ip[0] >> 4 == 4:
        head, total, proto = (ip[0] & 15) * 4, struct.unpack(">H", ip[2:4])[0], ip[9]
        dst, rest = ipaddress.IPv4Address(ip[16:20]), ip[head:total or None]  # what follows `total` is PCAPdroid's trailer
    elif ip[0] >> 4 == 6 and len(ip) >= 40:
        proto, dst, rest = ip[6], ipaddress.IPv6Address(ip[24:40]), ip[40:40 + struct.unpack(">H", ip[4:6])[0]]
    else:
        return None
    if proto == 6 and len(rest) >= 20:
        return "tcp", dst, *struct.unpack(">HH", rest[:4]), rest[(rest[12] >> 4) * 4:]
    if proto == 17 and len(rest) >= 8:
        return "udp", dst, *struct.unpack(">HH", rest[:4]), rest[8:]
    return None


def sni(p):
    """The server name of a TLS ClientHello, or None. Every length is checked: a capture is untrusted bytes."""
    try:
        if p[0] != 0x16 or p[5] != 0x01:
            return None
        i = 5 + 4 + 2 + 32                    # record header, handshake header, version, random
        i += 1 + p[i]                         # session id
        i += 2 + struct.unpack(">H", p[i:i + 2])[0]  # cipher suites
        i += 1 + p[i]                         # compression methods
        end = i + 2 + struct.unpack(">H", p[i:i + 2])[0]
        i += 2
        while i + 4 <= min(end, len(p)):
            kind, size = struct.unpack(">HH", p[i:i + 4])
            if kind == 0:                     # server_name: list length, type 0, name length, name
                n = struct.unpack(">H", p[i + 7:i + 9])[0]
                name = p[i + 9:i + 9 + n].decode("ascii")
                return name.lower() if name and len(name) == n else None
            i += 4 + size
    except (IndexError, struct.error, UnicodeDecodeError):
        pass
    return None


def http_host(p):
    if not p.startswith(HTTP):
        return None
    head = p.split(b"\r\n\r\n", 1)[0].lower()
    at = head.find(b"\r\nhost:")
    if at < 0:
        return None
    host = head[at + 7:].split(b"\r\n", 1)[0].strip().decode("ascii", "replace")
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host or None


def dns_name(p):
    """The first question of a DNS query (not of an answer), or None."""
    try:
        if len(p) < 17 or p[2] & 0x80 or struct.unpack(">H", p[4:6])[0] < 1:
            return None
        labels, i = [], 12
        while p[i]:
            if p[i] > 63:
                return None
            labels.append(p[i + 1:i + 1 + p[i]].decode("ascii"))
            i += 1 + p[i]
        return ".".join(labels).lower() or None
    except (IndexError, UnicodeDecodeError):
        return None


def analyse(data):
    """{"names": {name: {"how": [...], "packets": n, "to": [addresses]}}, "quic": {address: packets}, "packets": n}."""
    names, quic, total = {}, collections.Counter(), 0
    for ip in packets(data):
        total += 1
        t = transport(ip)
        if not t:
            continue
        proto, dst, sport, dport, payload = t
        found = []
        if proto == "tcp" and payload:
            found = [(sni(payload), "tls"), (http_host(payload), "http")]
        elif proto == "udp" and dport == 53:
            found = [(dns_name(payload), "dns")]
        elif proto == "udp" and dport == 443 and payload and payload[0] & 0x80:
            quic[str(dst)] += 1
        for name, how in found:
            if name:
                row = names.setdefault(name, {"how": [], "packets": 0, "to": []})
                row["packets"] += 1
                row["how"] = sorted(set(row["how"]) | {how})
                row["to"] = sorted(set(row["to"]) | {str(dst)})
    return {"names": names, "quic": dict(quic), "packets": total}


def selftest():
    def tcp(payload, dport=443):
        return struct.pack(">HHIIBBHHH", 40000, dport, 0, 0, 5 << 4, 0x18, 0, 0, 0) + payload

    def v4(proto, body, dst="93.184.216.34"):
        return struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + len(body), 0, 0, 64, proto, 0, bytes([10, 0, 0, 2]), ipaddress.IPv4Address(dst).packed) + body

    def v6(proto, body):
        return struct.pack(">IHBB", 6 << 28, len(body), proto, 64) + bytes(16) + ipaddress.IPv6Address("2001:db8::1").packed + body

    def hello(name):
        ext = struct.pack(">HHHBH", 0, len(name) + 5, len(name) + 3, 0, len(name)) + name
        body = b"\x03\x03" + bytes(32) + b"\x00" + struct.pack(">H", 2) + b"\x13\x01" + b"\x01\x00" + struct.pack(">H", len(ext)) + ext
        return b"\x16\x03\x01" + struct.pack(">H", len(body) + 4) + b"\x01" + len(body).to_bytes(3, "big") + body

    query = struct.pack(">HHHHHH", 7, 0x0100, 1, 0, 0, 0) + b"\x07f-droid\x03org\x00" + struct.pack(">HH", 1, 1)
    answer = struct.pack(">HHHHHH", 7, 0x8180, 1, 1, 0, 0) + b"\x07ignored\x03org\x00"
    frames = [v4(6, tcp(hello(b"Example.ORG"))) + b"PCAPDROID-TRAILER-BYTES",       # the trailer after the IP length is ignored
              v6(6, tcp(b"GET / HTTP/1.1\r\nUser-Agent: x\r\nHost: neverssl.com:80\r\n\r\n", 80)),
              v4(17, struct.pack(">HHHH", 40000, 53, 8 + len(query), 0) + query, "94.140.14.14"),
              v4(17, struct.pack(">HHHH", 53, 40000, 8 + len(answer), 0) + answer),
              v4(17, struct.pack(">HHHH", 40000, 443, 9, 0) + b"\xc0", "142.250.1.1"),  # QUIC long header: no name
              v4(6, tcp(b"\x16\x03\x01\x00\x05\x01\x00")),                           # a cut ClientHello: no crash, no name
              b"\x45"]                                                               # a cut packet
    for order, magic in (("<", b"\xd4\xc3\xb2\xa1"), (">", b"\xa1\xb2\xc3\xd4")):
        pcap = magic + struct.pack(order + "HHiIII", 2, 4, 0, 0, 65535, 101)
        pcap += b"".join(struct.pack(order + "IIII", 0, 0, len(f), len(f)) + f for f in frames)
        got = analyse(pcap)
        assert got["names"] == {"example.org": {"how": ["tls"], "packets": 1, "to": ["93.184.216.34"]},
                                "neverssl.com": {"how": ["http"], "packets": 1, "to": ["2001:db8::1"]},
                                "f-droid.org": {"how": ["dns"], "packets": 1, "to": ["94.140.14.14"]}}, got
        assert got["quic"] == {"142.250.1.1": 1} and got["packets"] == len(frames), got
    eth = b"\xd4\xc3\xb2\xa1" + struct.pack("<HHiIII", 2, 4, 0, 0, 65535, 1)
    frame = bytes(12) + b"\x08\x00" + frames[0]
    assert "example.org" in analyse(eth + struct.pack("<IIII", 0, 0, len(frame), len(frame)) + frame)["names"]
    for bad in (b"", b"\x0a\x0d\x0d\x0a" + bytes(40)):
        try:
            analyse(bad)
            raise AssertionError("a file that is not a pcap was read")
        except ValueError:
            pass
    print("pcap_domains self-check: OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
        sys.exit(0)
    if not sys.argv[1:] or sys.argv[1].startswith("-"):
        sys.exit(__doc__)
    with open(sys.argv[1], "rb") as f:
        result = analyse(f.read())
    if "--json" in sys.argv:
        print(json.dumps(result, indent=1))
        sys.exit(0)
    print(f"{result['packets']} packets, {len(result['names'])} names in clear, {len(result['quic'])} QUIC addresses (name not readable)")
    for name, row in sorted(result["names"].items(), key=lambda kv: -kv[1]["packets"]):
        print(f"  {row['packets']:5}  {'+'.join(row['how']):8} {name}  ->  {', '.join(row['to'][:4])}{' …' if len(row['to']) > 4 else ''}")
    for address, n in sorted(result["quic"].items(), key=lambda kv: -kv[1]):
        print(f"  {n:5}  quic     (name not readable)  ->  {address}")
