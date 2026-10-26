"""
Monitor de tráfego do projeto DAC: sniffer + janela de 1 s + MQTT.

A cada segundo soma os bytes capturados, calcula a ocupação da rede e
envia a mensagem do contrato de dados (OCUP,...) para o ESP32 no Wokwi.

Requisitos: sniffer_basico.py e publicador.py na MESMA pasta deste arquivo.

Uso:
    python monitor.py                       # captura até Ctrl+C e envia ao ESP32
    python monitor.py --sem-mqtt            # só mostra as janelas (sem enviar)
    python monitor.py --capacidade 200000   # referência de 200 kbit/s (alerta mais fácil)
    python monitor.py --media 3             # ocupação = média dos últimos 3 s (menos "piscadas")
    python monitor.py --duracao 30          # para sozinho depois de 30 s
    python monitor.py --iface "Wi-Fi"       # escolhe a interface
"""

import argparse
import threading
import time
from collections import deque

from scapy.all import AsyncSniffer

import publicador
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
    print("Monitor finalizado.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Monitor de tráfego do projeto DAC")
    parser.add_argument("--iface", default=None, help="interface de rede (veja sniffer_basico.py --listar)")
    parser.add_argument("--capacidade", type=int, default=publicador.CAPACIDADE_REF_BPS,
                        help="capacidade de referência em bit/s (padrão: 1000000)")
    parser.add_argument("--media", type=int, default=1,
                        help="nº de janelas de 1 s usadas na média móvel da ocupação (padrão: 1 = sem suavização)")
    parser.add_argument("--duracao", type=float, default=0, help="segundos de execução (0 = até Ctrl+C)")
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

    janela = Janela()
    sniffer = AsyncSniffer(
        prn=lambda pacote: janela.adicionar(extrair_registro(pacote)),
        store=False,
        iface=argumentos.iface,
    )

    suavizacao = f", média das últimas {argumentos.media} janelas" if argumentos.media > 1 else ""
    print(f"Referência de ocupação: {argumentos.capacidade:,} bit/s{suavizacao}. Ctrl+C para parar.\n")
    sniffer.start()
    time.sleep(0.5)
    if not sniffer.running:
        print("Não foi possível iniciar a captura (Npcap instalado? Tente como administrador).")
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

            pacotes, bytes_ = janela.fechar()
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())