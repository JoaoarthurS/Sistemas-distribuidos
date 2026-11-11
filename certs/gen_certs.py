#!/usr/bin/env python3
"""
Gera a infraestrutura de chaves de TESTE do SD Chat:

  ca.key / ca.crt          autoridade certificadora (CA) própria, válida 1 ano
  server.key / server.crt  certificado do servidor assinado pela CA

O certificado do servidor inclui no SAN: localhost, 127.0.0.1, ::1, o nome da
máquina e os IPs locais (para testes em rede). IPs/nomes extras podem ser
passados com --san. Os clientes confiam APENAS em ca.crt e validam o nome/IP
do servidor contra o SAN.

Uso:  pip install cryptography
      python certs/gen_certs.py [--san 192.168.0.10 --san meu-pc]
"""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import socket
import sys
from pathlib import Path

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
except ImportError:  # pragma: no cover
    raise SystemExit("Instale a dependência primeiro:  pip install cryptography")

OUT = Path(__file__).resolve().parent


def write_key(path: Path, key) -> None:
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                       serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))


def write_cert(path: Path, cert: x509.Certificate) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def local_names(extra: list[str]) -> tuple[list[str], list[str]]:
    dns = {"localhost"}
    ips = {"127.0.0.1", "::1"}
    host = socket.gethostname()
    if host:
        dns.add(host)
    try:
        ips.update(i for i in socket.gethostbyname_ex(host)[2] if not i.startswith("169.254."))
    except OSError:
        pass
    for item in extra:
        try:
            ipaddress.ip_address(item)
            ips.add(item)
        except ValueError:
            dns.add(item)
    return sorted(dns), sorted(ips)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--san", action="append", default=[], help="IP ou nome DNS extra do servidor")
    ap.add_argument("--days", type=int, default=365)
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    now = dt.datetime.now(dt.timezone.utc)
    until = now + dt.timedelta(days=args.days)

    # ---- CA -------------------------------------------------------------
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SD Chat - Unimontes (teste)"),
        x509.NameAttribute(NameOID.COMMON_NAME, "SD Chat Test CA"),
    ])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(until)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                     content_commitment=False, key_encipherment=False,
                                     data_encipherment=False, key_agreement=False,
                                     encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    # ---- servidor -------------------------------------------------------
    dns, ips = local_names(args.san)
    srv_key = ec.generate_private_key(ec.SECP256R1())
    san = x509.SubjectAlternativeName(
        [x509.DNSName(d) for d in dns] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips])
    srv_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SD Chat - Unimontes (teste)"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ]))
        .issuer_name(ca_name)
        .public_key(srv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(until)
        .add_extension(san, critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    write_key(OUT / "ca.key", ca_key)
    write_cert(OUT / "ca.crt", ca_cert)
    write_key(OUT / "server.key", srv_key)
    write_cert(OUT / "server.crt", srv_cert)

    fp = lambda c: c.fingerprint(hashes.SHA256()).hex(":").upper()  # noqa: E731
    print(f"Certificados gerados em {OUT}")
    print(f"  CA:       {ca_cert.subject.rfc4514_string()}")
    print(f"            SHA-256 {fp(ca_cert)}")
    print(f"  Servidor: {srv_cert.subject.rfc4514_string()}")
    print(f"            SHA-256 {fp(srv_cert)}")
    print(f"            SAN DNS={', '.join(dns)}")
    print(f"            SAN IP ={', '.join(ips)}")
    print(f"  Validade: até {until:%d/%m/%Y}")
    print("Distribua apenas ca.crt aos clientes. Nunca compartilhe as chaves (*.key).")


if __name__ == "__main__":
    main()
