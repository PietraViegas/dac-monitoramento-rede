"""
Sniffer básico do projeto DAC - monitoramento de tráfego de rede.

Captura pacotes da rede e imprime um por linha. Ainda não usa fila,
árvore nem MQTT: serve só para ver os dados reais aparecendo.

Requisitos (Windows): Npcap instalado + pip install scapy

Uso:
    python sniffer_basico.py --listar            # mostra as interfaces de rede
    python sniffer_basico.py                     # captura 50 pacotes e para
    python sniffer_basico.py --limite 200        # captura 200 pacotes
    python sniffer_basico.py --limite 0          # captura até Ctrl+C
    python sniffer_basico.py --iface "Wi-Fi"     # escolhe a interface
    python sniffer_basico.py --filtro "icmp or icmp6"   # só ping (filtro BPF)
"""

import argparse
import time
from collections import defaultdict

from scapy.all import ICMP, IP, TCP, UDP, conf, sniff
from scapy.layers.inet6 import IPv6, _ICMPv6

PROTOCOLOS = ["TCP", "UDP", "ICMP", "OUTROS"]


def extrair_registro(pacote):
    """Transforma um pacote do Scapy no registro do contrato de dados.

    Campos: momento, ip_origem, ip_destino, protocolo, tamanho.
    O tamanho é len(pacote): bytes do pacote inteiro, incluindo cabeçalhos.
    Aceita IPv4 e IPv6. ICMPv6 é contado como ICMP.
    Tudo que não for TCP/UDP/ICMP (ex: ARP) é classificado como "OUTROS".
    """
    protocolo = "OUTROS"
    ip_origem = None
    ip_destino = None

    if IP in pacote:
        ip_origem = pacote[IP].src
        ip_destino = pacote[IP].dst
    elif IPv6 in pacote:
        ip_origem = pacote[IPv6].src
        ip_destino = pacote[IPv6].dst

    if ip_origem is not None:
        if TCP in pacote:
            protocolo = "TCP"
        elif UDP in pacote:
            protocolo = "UDP"
        elif ICMP in pacote or any(isinstance(c, _ICMPv6) for c in pacote.iterpayloads()):
            protocolo = "ICMP"

    return {
        "momento": float(pacote.time),
        "ip_origem": ip_origem,
        "ip_destino": ip_destino,
        "protocolo": protocolo,
        "tamanho": len(pacote),
    }


def formatar_linha(registro):
    hora = time.strftime("%H:%M:%S", time.localtime(registro["momento"]))
    origem = registro["ip_origem"] or "-"
    destino = registro["ip_destino"] or "-"
    return (
        f"{hora}  {registro['protocolo']:<6} {registro['tamanho']:>5} bytes  "
        f"{origem} -> {destino}"
    )


def imprimir_resumo(contagem, bytes_por_protocolo, inicio):
    duracao = max(time.time() - inicio, 0.001)
    total_pacotes = sum(contagem.values())
    total_bytes = sum(bytes_por_protocolo.values())

    print("\n" + "=" * 52)
    print(f"RESUMO ({duracao:.1f} s de captura)")
    print("=" * 52)
    print(f"{'Protocolo':<10}{'Pacotes':>10}{'Bytes':>12}")
    for protocolo in PROTOCOLOS:
        print(f"{protocolo:<10}{contagem[protocolo]:>10}{bytes_por_protocolo[protocolo]:>12}")
    print(f"{'TOTAL':<10}{total_pacotes:>10}{total_bytes:>12}")

    # OUTROS (ex: ARP) não entra na ocupação, conforme o contrato
    bytes_monitorados = total_bytes - bytes_por_protocolo["OUTROS"]
    taxa_bps = bytes_monitorados * 8 / duracao
    print(f"\nTaxa média TCP+UDP+ICMP: {taxa_bps:,.0f} bit/s")


def main():
    parser = argparse.ArgumentParser(description="Sniffer básico do projeto DAC")
    parser.add_argument("--listar", action="store_true", help="lista as interfaces de rede e sai")
    parser.add_argument("--iface", default=None, help="nome da interface (veja --listar)")
    parser.add_argument("--limite", type=int, default=50,
                        help="quantidade de pacotes (0 = até Ctrl+C). Padrão: 50")
    parser.add_argument("--filtro", default=None,
                        help='filtro BPF opcional, ex: "icmp or icmp6", "udp", "tcp port 443"')
    argumentos = parser.parse_args()

    if argumentos.listar:
        print(conf.ifaces)
        return

    contagem = defaultdict(int)
    bytes_por_protocolo = defaultdict(int)

    def ao_capturar(pacote):
        registro = extrair_registro(pacote)
        contagem[registro["protocolo"]] += 1
        bytes_por_protocolo[registro["protocolo"]] += registro["tamanho"]
        print(formatar_linha(registro))

    interface = argumentos.iface or conf.iface
    print(f"Capturando na interface: {interface}")
    print("Gere tráfego (abra um site, rode 'ping 8.8.8.8') e use Ctrl+C para parar.\n")

    inicio = time.time()
    try:
        sniff(prn=ao_capturar, store=False, iface=argumentos.iface,
              count=argumentos.limite, filter=argumentos.filtro)
    except KeyboardInterrupt:
        pass
    except PermissionError:
        print("Sem permissão para capturar. Abra o terminal como administrador.")
        return

    imprimir_resumo(contagem, bytes_por_protocolo, inicio)


if __name__ == "__main__":
    main()