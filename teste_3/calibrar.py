"""
Calibração da capacidade de referência (decisão D11 do relatório).

Mede o tráfego do seu PC em 3 cenários guiados e recomenda o valor da
capacidade de referência, usando uma regra explícita:

  1. Os cenários "Normal" e "Vídeo" devem ficar abaixo de 80% da referência
     (em 95% das janelas), usando a média móvel configurada.
  2. O cenário "Gargalo" (speedtest) deve passar de 80% em pelo menos
     75% das janelas.
  3. Entre os valores redondos que respeitam as duas regras (com 25% de
     folga sobre o mínimo), escolhe o MENOR, para o display se mexer mais.

Requisitos: sniffer_basico.py na mesma pasta, Npcap e scapy instalados.

Uso:
    python calibrar.py                 # 3 cenários de 30 s cada
    python calibrar.py --segundos 20   # cenários mais curtos
    python calibrar.py --media 5       # testa com média móvel de 5 s

Ao final grava calibracao_resultado.txt (anexe no Trello e use na D11).
"""

import argparse
import math
import threading
import time

from scapy.all import AsyncSniffer

from sniffer_basico import extrair_registro

JANELA_S = 1.0
MONITORADOS = ("TCP", "UDP", "ICMP")
LIMITE_ALERTA = 0.8          # alerta a partir de 80% da referência
FOLGA = 1.25                 # margem sobre o mínimo
REFERENCIAS = [500_000, 1_000_000, 2_000_000, 5_000_000,
               10_000_000, 20_000_000, 50_000_000, 100_000_000]

CENARIOS = [
    ("Normal", "Deixe o PC parado ou navegando de leve (sem vídeo nem download)."),
    ("Vídeo", "Abra um vídeo no YouTube e deixe rodando."),
    ("Gargalo", "Rode um teste de velocidade (speedtest) ou um download grande."),
]


def coletar(segundos, iface=None):
    """Captura por N janelas de 1 s. Devolve uma lista de (bytes, duração)."""
    trava = threading.Lock()
    acumulado = [0]

    def ao_capturar(pacote):
        registro = extrair_registro(pacote)
        if registro["protocolo"] in MONITORADOS:
            with trava:
                acumulado[0] += registro["tamanho"]

    sniffer = AsyncSniffer(prn=ao_capturar, store=False, iface=iface)
    sniffer.start()
    time.sleep(0.5)
    if not sniffer.running:
        raise RuntimeError("Não foi possível iniciar a captura (Npcap instalado? Tente como administrador).")

    with trava:
        acumulado[0] = 0
    janelas = []
    ultimo = time.monotonic()
    try:
        for i in range(segundos):
            time.sleep(JANELA_S)
            agora = time.monotonic()
            duracao, ultimo = agora - ultimo, agora
            with trava:
                bytes_janela, acumulado[0] = acumulado[0], 0
            janelas.append((bytes_janela, duracao))
            print(f"  {i + 1:>3}/{segundos}  {bytes_janela * 8 / duracao / 1000:>10.1f} kbit/s")
    except KeyboardInterrupt:
        print("  (interrompido; usando o que foi medido)")
    finally:
        if sniffer.running:
            sniffer.stop()
    return janelas


def taxas_media(janelas, n):
    """Taxa (bit/s) de cada janela, usando a média das últimas n janelas."""
    saida = []
    for i in range(len(janelas)):
        trecho = janelas[max(0, i - n + 1): i + 1]
        total_bytes = sum(b for b, _ in trecho)
        total_tempo = sum(d for _, d in trecho)
        saida.append(total_bytes * 8 / total_tempo)
    return saida


def percentil(valores, p):
    """Percentil pelo método do posto mais próximo (sem bibliotecas externas)."""
    ordenados = sorted(valores)
    posicao = max(0, math.ceil(p / 100 * len(ordenados)) - 1)
    return ordenados[posicao]


def recomendar(cenarios, media):
    """cenarios: dict nome -> lista de (bytes, duração). Devolve o resultado da regra."""
    mm = {nome: taxas_media(janelas, media) for nome, janelas in cenarios.items()}

    base = max(percentil(mm["Normal"], 95), percentil(mm["Vídeo"], 95))
    minimo = base / LIMITE_ALERTA                      # abaixo disso, vídeo/normal dariam alerta
    maximo = percentil(mm["Gargalo"], 25) / LIMITE_ALERTA  # acima disso, o speedtest não daria alerta

    candidatos = [r for r in REFERENCIAS if minimo * FOLGA <= r <= maximo]
    if candidatos:
        escolhida, viavel = min(candidatos), True
    else:
        alvo = math.sqrt(minimo * maximo) if minimo > 0 and maximo > 0 else max(minimo, maximo, REFERENCIAS[0])
        escolhida = min(REFERENCIAS, key=lambda r: abs(math.log(r / alvo)))
        viavel = False

    return {"mm": mm, "minimo": minimo, "maximo": maximo, "escolhida": escolhida, "viavel": viavel}


def mbps(bps):
    return f"{bps / 1e6:.2f}"


def montar_relatorio(cenarios, resultado, media):
    linhas = []
    linhas.append("CALIBRAÇÃO DA CAPACIDADE DE REFERÊNCIA (D11)")
    linhas.append(f"Gerado em {time.strftime('%d/%m/%Y %H:%M')} | média móvel: {media} janelas de 1 s")
    linhas.append("")
    linhas.append("Taxas medidas (TCP+UDP+ICMP), em Mbit/s")
    linhas.append("")
    linhas.append("| Cenário | Janelas | Média | Mediana | p95 | Máximo | p95 da média móvel |")
    linhas.append("|---|---|---|---|---|---|---|")
    for nome, janelas in cenarios.items():
        taxas = [b * 8 / d for b, d in janelas]
        linhas.append(
            f"| {nome} | {len(janelas)} | {mbps(sum(taxas) / len(taxas))} | {mbps(percentil(taxas, 50))} | "
            f"{mbps(percentil(taxas, 95))} | {mbps(max(taxas))} | {mbps(percentil(resultado['mm'][nome], 95))} |"
        )
    linhas.append("")
    linhas.append("Regra aplicada")
    linhas.append(f"- Mínimo (Normal e Vídeo abaixo de 80% em 95% das janelas): {mbps(resultado['minimo'])} Mbit/s")
    linhas.append(f"- Máximo (Gargalo acima de 80% em 75% das janelas): {mbps(resultado['maximo'])} Mbit/s")
    linhas.append(f"- Folga aplicada sobre o mínimo: {int((FOLGA - 1) * 100)}%")
    linhas.append("")
    escolhida = resultado["escolhida"]
    if resultado["viavel"]:
        linhas.append(f"REFERÊNCIA RECOMENDADA: {escolhida / 1e6:g} Mbit/s")
        linhas.append(f"Comando: python monitor.py --capacidade {escolhida} --media {media}")
        linhas.append(f"No publicador.py: CAPACIDADE_REF_BPS = {escolhida:_}")
    else:
        linhas.append(f"ATENÇÃO: não existe valor redondo que satisfaça as duas regras (faixa {mbps(resultado['minimo'])} a {mbps(resultado['maximo'])} Mbit/s).")
        linhas.append(f"Valor mais próximo da faixa: {escolhida / 1e6:g} Mbit/s (use com cautela).")
        linhas.append("Causas comuns: o speedtest não saturou a conexão (refaça com um download grande)")
        linhas.append("ou o vídeo gerou tráfego muito alto. Tente --media 5 ou repita os cenários.")
    linhas.append("")
    linhas.append("Frase pronta para a decisão D11:")
    linhas.append(
        f"“A capacidade de referência é didática, de {escolhida / 1e6:g} Mbit/s, escolhida a partir do tráfego medido "
        f"em três cenários (normal: p95 de {mbps(percentil(resultado['mm']['Normal'], 95))} Mbit/s; "
        f"vídeo: p95 de {mbps(percentil(resultado['mm']['Vídeo'], 95))} Mbit/s; "
        f"speedtest: mediana de {mbps(percentil(resultado['mm']['Gargalo'], 50))} Mbit/s), com média móvel de {media} s.”"
    )
    return "\n".join(linhas)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Calibração da capacidade de referência")
    parser.add_argument("--segundos", type=int, default=30, help="duração de cada cenário (padrão: 30)")
    parser.add_argument("--media", type=int, default=3, help="janelas da média móvel (padrão: 3)")
    parser.add_argument("--iface", default=None, help="interface de rede")
    argumentos = parser.parse_args(argv)

    print("Dica: pause o OneDrive e feche programas pesados antes de começar.\n")
    cenarios = {}
    for nome, instrucao in CENARIOS:
        print(f"=== Cenário: {nome} ===")
        print(instrucao)
        input("Pressione Enter para começar a medir... ")
        cenarios[nome] = coletar(argumentos.segundos, argumentos.iface)
        print()
        if not cenarios[nome]:
            print("Nenhuma janela medida; repita o cenário.")
            return 1

    resultado = recomendar(cenarios, argumentos.media)
    texto = montar_relatorio(cenarios, resultado, argumentos.media)
    print("\n" + "=" * 60)
    print(texto)
    with open("calibracao_resultado.txt", "w", encoding="utf-8") as arquivo:
        arquivo.write(texto + "\n")
    print("\nSalvo em calibracao_resultado.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())