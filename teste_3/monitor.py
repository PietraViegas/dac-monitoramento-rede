"""
Monitor de tráfego do projeto DAC: sniffer + janela de 1 s + MQTT.

O sniffer coloca cada pacote numa fila dinâmica (buffer). A cada segundo o
monitor esvazia a fila, soma os bytes da janela, calcula a ocupação da rede e
envia a mensagem do contrato de dados (OCUP,...) para o ESP32 no Wokwi.
Os pacotes também vão para uma árvore binária de busca por IP; ao parar, o
monitor mostra o relatório de banda por protocolo e o top de consumidores
(IPs ordenados com QuickSort). Com --log, cada pacote é gravado num arquivo CSV
que, ao parar, é comprimido com Huffman.

Requisitos: sniffer_basico.py, publicador.py, estruturas.py e huffman.py na MESMA pasta deste arquivo.

Uso:
    python monitor.py                       # captura até Ctrl+C e envia ao ESP32
    python monitor.py --sem-mqtt            # só mostra as janelas (sem enviar)
    python monitor.py --capacidade 200000   # referência de 200 kbit/s (alerta mais fácil)
    python monitor.py --media 3             # ocupação = média dos últimos 3 s (menos "piscadas")
    python monitor.py --duracao 30          # para sozinho depois de 30 s
    python monitor.py --iface "Wi-Fi"       # escolhe a interface
    python monitor.py --top 5               # mostra só os 5 maiores consumidores ao parar
    python monitor.py --log                 # grava trafego_log.csv e comprime em trafego_log.csv.huf
    python monitor.py --log meu_log.csv     # escolhe o nome do log
"""

import argparse
import threading
import time
from collections import deque

from scapy.all import AsyncSniffer

import huffman
import publicador
from estruturas import ArvoreIP, Fila, top_consumidores
from sniffer_basico import extrair_registro

MONITORADOS = ["TCP", "UDP", "ICMP"]
TODOS = MONITORADOS + ["OUTROS"]
JANELA_S = 1.0


class Janela:
    """Acumula pacotes e bytes por protocolo durante uma janela de tempo."""

    def __init__(self):
        self._trava = threading.Lock()
        self._zerar()

    def _zerar(self):
        self._pacotes = {p: 0 for p in TODOS}
        self._bytes = {p: 0 for p in TODOS}

    def adicionar(self, registro):
        with self._trava:
            self._pacotes[registro["protocolo"]] += 1
            self._bytes[registro["protocolo"]] += registro["tamanho"]

    def fechar(self):
        """Devolve (pacotes, bytes) da janela e começa uma nova."""
        with self._trava:
            resultado = (dict(self._pacotes), dict(self._bytes))
            self._zerar()
        return resultado


class Relatorio:
    """Soma as janelas de toda a execução para o relatório de banda por protocolo."""

    def __init__(self):
        self.pacotes = {p: 0 for p in TODOS}
        self.bytes = {p: 0 for p in TODOS}
        self.duracao = 0.0

    def somar(self, pacotes, bytes_, duracao):
        for p in TODOS:
            self.pacotes[p] += pacotes[p]
            self.bytes[p] += bytes_[p]
        self.duracao += duracao

    def linhas(self):
        duracao = max(self.duracao, 0.001)
        total_bytes = sum(self.bytes.values())
        saida = [
            f"RELATÓRIO DE BANDA POR PROTOCOLO ({self.duracao:.1f} s de captura)",
            f"{'Protocolo':<10}{'Pacotes':>10}{'Bytes':>14}{'Média kbit/s':>14}{'% dos bytes':>13}",
        ]
        for p in TODOS + ["TOTAL"]:
            pacotes = sum(self.pacotes.values()) if p == "TOTAL" else self.pacotes[p]
            bytes_ = total_bytes if p == "TOTAL" else self.bytes[p]
            fatia = bytes_ / total_bytes * 100 if total_bytes else 0.0
            saida.append(
                f"{p:<10}{pacotes:>10,}{bytes_:>14,}{bytes_ * 8 / duracao / 1000:>14.1f}{fatia:>12.1f}%"
            )
        monitorados = sum(self.bytes[p] for p in MONITORADOS)
        saida.append(f"Ocupação usa só TCP+UDP+ICMP: média de {monitorados * 8 / duracao / 1000:.1f} kbit/s")
        return saida


def formatar_log(registro):
    """Linha CSV do log: hora,protocolo,tamanho,origem,destino."""
    momento = registro["momento"]
    hora = time.strftime("%H:%M:%S", time.localtime(momento)) + f".{int(momento * 1000) % 1000:03d}"
    return (
        f"{hora},{registro['protocolo']},{registro['tamanho']},"
        f"{registro['ip_origem'] or '-'},{registro['ip_destino'] or '-'}\n"
    )


def processar_fila(fila, janela, arvore, log=None):
    """Tira da fila tudo o que o sniffer capturou e distribui na janela, na árvore e no log."""
    while True:
        registro = fila.desenfileirar()
        if registro is None:
            return
        janela.adicionar(registro)
        if log is not None:
            log.write(formatar_log(registro))
        if registro["protocolo"] in MONITORADOS:  # mesma regra da ocupação
            arvore.registrar(registro)


def imprimir_top(arvore, fila, n):
    consumidores = top_consumidores(arvore, n)
    print(f"\nTOP {len(consumidores)} CONSUMIDORES (bytes enviados + recebidos, TCP+UDP+ICMP)")
    print(f"{'#':>3}  {'IP':<40}{'Pacotes':>9}{'Enviados':>14}{'Recebidos':>14}{'Total':>14}")
    for posicao, c in enumerate(consumidores, start=1):
        print(
            f"{posicao:>3}  {c['ip']:<40}{c['pacotes']:>9}{c['bytes_enviados']:>14,}"
            f"{c['bytes_recebidos']:>14,}{c['bytes_total']:>14,}"
        )
    print(f"\nÁrvore: {len(arvore)} IPs, altura {arvore.altura()}. "
          f"Fila: pico de {fila.maior_tamanho} pacotes esperando.")


def formatar_janela(pacotes, taxa_kbps, mensagem):
    _, ocupacao, nivel, alerta, _ = mensagem.split(",")
    protocolos = "  ".join(f"{p} {pacotes[p]:>4}" for p in TODOS)
    cor = "VERMELHO" if alerta == "1" else "verde"
    return (
        f"{time.strftime('%H:%M:%S')}  {protocolos}  | "
        f"{taxa_kbps:>8.1f} kbit/s | ocupação {float(ocupacao):>5.1f}% | "
        f"nível {nivel} {cor}"
    )


def encerrar(cliente, sniffer):
    """Limpeza ao parar. Avisa o ESP32 primeiro; Ctrl+C repetido aqui é ignorado."""
    print("\nEncerrando, aguarde...")
    passos = []
    if cliente:
        def avisar_sem_dados():
            info = cliente.publish(publicador.TOPICO, publicador.MENSAGEM_SEM_DADOS, qos=0, retain=False)
            info.wait_for_publish(timeout=2)
        passos.append(avisar_sem_dados)  # display do ESP32 volta ao traço na hora
    passos.append(lambda: sniffer.stop() if sniffer.running else None)
    if cliente:
        passos += [cliente.loop_stop, cliente.disconnect]
    for passo in passos:
        try:
            passo()
        except (KeyboardInterrupt, Exception):
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Monitor de tráfego do projeto DAC")
    parser.add_argument("--iface", default=None, help="interface de rede (veja sniffer_basico.py --listar)")
    parser.add_argument("--capacidade", type=int, default=publicador.CAPACIDADE_REF_BPS,
                        help=f"capacidade de referência em bit/s (padrão: {publicador.CAPACIDADE_REF_BPS})")
    parser.add_argument("--media", type=int, default=1,
                        help="nº de janelas de 1 s usadas na média móvel da ocupação (padrão: 1 = sem suavização)")
    parser.add_argument("--duracao", type=float, default=0, help="segundos de execução (0 = até Ctrl+C)")
    parser.add_argument("--top", type=int, default=10,
                        help="quantos IPs mostrar no top de consumidores ao parar (0 = não mostra)")
    parser.add_argument("--log", nargs="?", const="trafego_log.csv", default=None, metavar="ARQUIVO",
                        help="grava cada pacote num CSV e comprime com Huffman ao parar (padrão: trafego_log.csv)")
    parser.add_argument("--sem-mqtt", action="store_true", help="não conecta ao MQTT, só mostra as janelas")
    argumentos = parser.parse_args(argv)

    if argumentos.media < 1:
        parser.error("--media precisa ser 1 ou mais")
    publicador.CAPACIDADE_REF_BPS = argumentos.capacidade

    cliente = None
    if not argumentos.sem_mqtt:
        try:
            cliente = publicador.criar_cliente()
        except OSError as erro:
            print(f"Não foi possível conectar ao MQTT ({erro}). Use --sem-mqtt para testar só a captura.")
            return 1
        print(f"MQTT conectado: {publicador.BROKER}, tópico {publicador.TOPICO}")

    log = None
    if argumentos.log:
        try:
            log = open(argumentos.log, "w", encoding="utf-8")
        except OSError as erro:
            print(f"Não foi possível criar o log ({erro}).")
            if cliente:
                cliente.loop_stop()
                cliente.disconnect()
            return 1
        log.write("hora,protocolo,tamanho,origem,destino\n")
        print(f"Gravando os pacotes em {argumentos.log}")

    janela = Janela()
    fila = Fila()
    arvore = ArvoreIP()
    relatorio = Relatorio()
    sniffer = AsyncSniffer(
        prn=lambda pacote: fila.enfileirar(extrair_registro(pacote)),
        store=False,
        iface=argumentos.iface,
    )

    suavizacao = f", média das últimas {argumentos.media} janelas" if argumentos.media > 1 else ""
    print(f"Referência de ocupação: {argumentos.capacidade:,} bit/s{suavizacao}. Ctrl+C para parar.\n")
    sniffer.start()
    time.sleep(0.5)
    if not sniffer.running:
        print("Não foi possível iniciar a captura (Npcap instalado? Tente como administrador).")
        if log:
            log.close()
        if cliente:
            cliente.loop_stop()
            cliente.disconnect()
        return 1

    historico = deque(maxlen=argumentos.media)  # (bytes, duração) das últimas janelas
    inicio = ultimo = time.monotonic()
    try:
        while True:
            time.sleep(JANELA_S)
            agora = time.monotonic()
            duracao, ultimo = agora - ultimo, agora

            if not sniffer.running:
                print("A captura parou inesperadamente.")
                break

            processar_fila(fila, janela, arvore, log)
            pacotes, bytes_ = janela.fechar()
            relatorio.somar(pacotes, bytes_, duracao)
            bytes_monitorados = sum(bytes_[p] for p in MONITORADOS)
            historico.append((bytes_monitorados, duracao))
            bytes_media = sum(b for b, _ in historico)
            duracao_media = sum(d for _, d in historico)
            mensagem = publicador.montar_mensagem(bytes_media, duracao_media)
            taxa_kbps = bytes_media * 8 / duracao_media / 1000

            if cliente:
                cliente.publish(publicador.TOPICO, mensagem, qos=0, retain=False)
            print(formatar_janela(pacotes, taxa_kbps, mensagem))

            if argumentos.duracao and (agora - inicio) >= argumentos.duracao:
                break
    except KeyboardInterrupt:
        pass
    finally:
        encerrar(cliente, sniffer)
        try:
            processar_fila(fila, janela, arvore, log)  # pacotes que chegaram depois da última janela
            pacotes, bytes_ = janela.fechar()
            relatorio.somar(pacotes, bytes_, time.monotonic() - ultimo)
            print()
            print("\n".join(relatorio.linhas()))
            if argumentos.top > 0:
                imprimir_top(arvore, fila, argumentos.top)
            if log:
                log.close()
                print()
                print(huffman.formatar_estatisticas(huffman.comprimir_arquivo(argumentos.log)))
        except KeyboardInterrupt:
            pass
        finally:
            if log:
                log.close()
        print("Monitor finalizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())