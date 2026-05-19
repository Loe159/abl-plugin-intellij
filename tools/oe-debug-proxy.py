"""
OE Debug Protocol Proxy — capture le trafic entre PDSOE et OpenEdge.

Usage :
  1. Lancer OE avec -debugReady sur un port (ex. 3075) :
       _progres.exe -b -p votre_prog.p -debugReady 3075
     ou sans -b pour mode interactif :
       _progres.exe -p votre_prog.p -debugReady 3075

  2. Lancer ce proxy :
       python oe-debug-proxy.py --oe-port 3075 --proxy-port 3076

  3. Dans PDSOE, se connecter à localhost:3076 (au lieu de 3075)

  4. Effectuer les opérations debug (poser un breakpoint, F5, step, inspecter une variable...)

  5. Le trafic complet est loggé dans oe-debug-capture.log (hex + ASCII)

Conseil d'opérations à faire pendant la capture :
  - Connexion initiale (handshake)
  - Poser un breakpoint sur une ligne précise
  - Lancer le programme (GO/F5)
  - Le programme s'arrête au breakpoint
  - Inspecter une variable locale simple (INTEGER, CHARACTER)
  - Step Over (F6)
  - Step Into (F7)
  - Step Out (F8)
  - Reprendre l'exécution (F5)
  - Déconnecter proprement
"""

import socket
import threading
import sys
import time
import argparse
from datetime import datetime

LOG_FILE = "oe-debug-capture.log"
MSG_COUNTER = [0]

def hex_dump(data: bytes, label: str, counter: int) -> str:
    lines = [f"\n{'='*70}"]
    lines.append(f"[{counter:04d}] {label} — {len(data)} bytes — {datetime.now().strftime('%H:%M:%S.%f')}")
    lines.append(f"{'='*70}")

    # Hex + ASCII sur 16 octets par ligne
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_part  = ' '.join(f'{b:02x}' for b in chunk)
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        lines.append(f"  {i:04x}  {hex_part:<47}  |{ascii_part}|")

    # Interprétation heuristique des 4 premiers octets (longueur potentielle)
    if len(data) >= 4:
        be_len = int.from_bytes(data[0:4], 'big')
        le_len = int.from_bytes(data[0:4], 'little')
        lines.append(f"  → Premiers 4 octets : big-endian={be_len}, little-endian={le_len}")
    if len(data) >= 6:
        msg_type_be = int.from_bytes(data[4:6], 'big')
        msg_type_le = int.from_bytes(data[4:6], 'little')
        lines.append(f"  → Octets 4-5 (type?) : big-endian={msg_type_be} (0x{msg_type_be:04x}), little-endian={msg_type_le}")

    # Chaînes ASCII lisibles dans le message
    ascii_strings = []
    i, current = 0, []
    while i < len(data):
        if 32 <= data[i] < 127:
            current.append(chr(data[i]))
        else:
            if len(current) >= 3:
                ascii_strings.append(''.join(current))
            current = []
        i += 1
    if len(current) >= 3:
        ascii_strings.append(''.join(current))
    if ascii_strings:
        lines.append(f"  → Chaînes ASCII : {ascii_strings}")

    return '\n'.join(lines)


def forward(src: socket.socket, dst: socket.socket, label: str, log_file):
    """Lit les données de src, les logue, et les envoie à dst."""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                print(f"[proxy] {label} — connexion fermée")
                break

            MSG_COUNTER[0] += 1
            dump = hex_dump(data, label, MSG_COUNTER[0])

            print(dump)
            log_file.write(dump + '\n')
            log_file.flush()

            dst.sendall(data)
    except Exception as e:
        print(f"[proxy] {label} erreur : {e}")
    finally:
        try: src.close()
        except: pass
        try: dst.close()
        except: pass


def handle_client(client_sock: socket.socket, oe_host: str, oe_port: int, log_file):
    """Ouvre la connexion vers OE et démarre les deux threads de forwarding."""
    print(f"[proxy] PDSOE connecté — connexion à OE {oe_host}:{oe_port}...")
    try:
        oe_sock = socket.create_connection((oe_host, oe_port), timeout=10)
        oe_sock.settimeout(None)  # reset to blocking — timeout=10 s'applique sinon à tous les recv()
        print(f"[proxy] Connexion OE établie")
    except Exception as e:
        print(f"[proxy] Impossible de joindre OE : {e}")
        client_sock.close()
        return

    t1 = threading.Thread(target=forward, args=(client_sock, oe_sock, "PDSOE → OE", log_file), daemon=True)
    t2 = threading.Thread(target=forward, args=(oe_sock, client_sock, "OE → PDSOE", log_file), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    print("[proxy] Session terminée")


def main():
    parser = argparse.ArgumentParser(description="OE Debug Protocol Proxy")
    parser.add_argument("--oe-host",    default="localhost", help="Hôte OE (défaut: localhost)")
    parser.add_argument("--oe-port",    type=int, default=3075, help="Port OE debugReady (défaut: 3075)")
    parser.add_argument("--proxy-port", type=int, default=3076, help="Port d'écoute du proxy (défaut: 3076)")
    parser.add_argument("--log",        default=LOG_FILE, help=f"Fichier de log (défaut: {LOG_FILE})")
    args = parser.parse_args()

    print(f"""
OE Debug Protocol Proxy
========================
  Écoute sur        : localhost:{args.proxy_port}
  Redirige vers OE  : {args.oe_host}:{args.oe_port}
  Log               : {args.log}

  → Dans PDSOE, connectez-vous à localhost:{args.proxy_port}
  → OE doit tourner avec : -debugReady {args.oe_port}
""")

    log_file = open(args.log, 'w', encoding='utf-8')
    log_file.write(f"OE Debug Capture — {datetime.now()}\n")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('localhost', args.proxy_port))
    server.listen(1)

    print(f"[proxy] En attente d'une connexion PDSOE sur port {args.proxy_port}...")
    try:
        while True:
            client_sock, addr = server.accept()
            print(f"[proxy] Connexion entrante de {addr}")
            t = threading.Thread(
                target=handle_client,
                args=(client_sock, args.oe_host, args.oe_port, log_file),
                daemon=True
            )
            t.start()
    except KeyboardInterrupt:
        print("\n[proxy] Arrêt")
    finally:
        server.close()
        log_file.close()
        print(f"[proxy] Log sauvegardé dans : {args.log}")


if __name__ == "__main__":
    main()
