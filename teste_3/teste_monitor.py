"""
Testes das partes do monitor.py que não dependem de capturar pacotes:
fila -> janela/árvore/log, relatório por protocolo e formato do log.

Precisa do Scapy instalado (o monitor importa), mas não captura nada,
então não precisa de administrador nem do Npcap rodando.

Uso:
    python teste_monitor.py
"""

import io
import random
from typing import Any

from estruturas import ArvoreIP, Fila
from monitor import MONITORADOS, TODOS, Janela, Relatorio, formatar_log, processar_fila


def registro_aleatorio() -> dict[str, Any]:
    protocolo = random.choice(TODOS)
    sem_ip = protocolo == "OUTROS" and random.random() < 0.5  # ex: ARP
    return {
        "momento": 1_761_000_000 + random.random() * 100,
        "ip_origem": None if sem_ip else f"10.0.0.{random.randint(1, 5)}",
        "ip_destino": None if sem_ip else f"8.8.8.{random.randint(1, 5)}",
        "protocolo": protocolo,
        "tamanho": random.randint(42, 1514),
    }


def teste_processar_fila():
    fila, janela, arvore, log = Fila(), Janela(), ArvoreIP(), io.StringIO()
    registros = [registro_aleatorio() for _ in range(2000)]
    for r in registros:
        fila.enfileirar(r)
    processar_fila(fila, janela, arvore, log)

    assert fila.vazia()
    pacotes, bytes_ = janela.fechar()
    for p in TODOS:
        assert pacotes[p] == sum(1 for r in registros if r["protocolo"] == p)
        assert bytes_[p] == sum(r["tamanho"] for r in registros if r["protocolo"] == p)

    # a árvore só conta TCP/UDP/ICMP (mesma regra da ocupação)
    monitorados = [r for r in registros if r["protocolo"] in MONITORADOS]
    enviados = sum(no["bytes_enviados"] for no in arvore.em_ordem())
    assert enviados == sum(r["tamanho"] for r in monitorados)

    # uma linha de log por pacote, inclusive OUTROS
    assert log.getvalue().count("\n") == len(registros)
    print("processar_fila: OK (janela, árvore e log batem com os 2000 pacotes)")


def teste_relatorio():
    relatorio = Relatorio()
    janelas = []
    for _ in range(30):
        pacotes = {p: random.randint(0, 100) for p in TODOS}
        bytes_ = {p: random.randint(0, 100_000) for p in TODOS}
        janelas.append((pacotes, bytes_))
        relatorio.somar(pacotes, bytes_, 1.0)

    for p in TODOS:
        assert relatorio.pacotes[p] == sum(j[0][p] for j in janelas)
        assert relatorio.bytes[p] == sum(j[1][p] for j in janelas)
    assert abs(relatorio.duracao - 30.0) < 1e-9

    linhas = relatorio.linhas()
    total = sum(relatorio.bytes.values())
    linha_total = next(l for l in linhas if l.startswith("TOTAL"))
    assert f"{total:,}" in linha_total and "100.0%" in linha_total

    tcp = relatorio.bytes["TCP"]
    linha_tcp = next(l for l in linhas if l.startswith("TCP"))
    assert f"{tcp * 8 / 30 / 1000:.1f}" in linha_tcp  # média em kbit/s

    vazio = Relatorio().linhas()  # sem pacotes não pode dividir por zero
    assert any(l.startswith("TOTAL") for l in vazio)
    print("Relatório por protocolo: OK (somas, médias, porcentagens e caso vazio)")


def teste_formatar_log():
    linha = formatar_log({"momento": 1_761_000_000.25, "ip_origem": "10.0.0.1",
                          "ip_destino": "8.8.8.8", "protocolo": "ICMP", "tamanho": 74})
    hora, protocolo, tamanho, origem, destino = linha.rstrip("\n").split(",")
    assert hora.endswith(".250") and len(hora) == 12
    assert (protocolo, tamanho, origem, destino) == ("ICMP", "74", "10.0.0.1", "8.8.8.8")

    sem_ip = formatar_log({"momento": 0.0, "ip_origem": None, "ip_destino": None,
                           "protocolo": "OUTROS", "tamanho": 42})
    assert sem_ip.endswith(",OUTROS,42,-,-\n")
    print("Formato do log: OK")


if __name__ == "__main__":
    teste_processar_fila()
    teste_relatorio()
    teste_formatar_log()
    print("\nTodos os testes passaram.")
