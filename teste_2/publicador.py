"""
Publicador de teste do projeto DAC - monitoramento de tráfego de rede.

Envia mensagens do contrato de dados para o ESP32 (Wokwi) via MQTT.

Uso:
    pip install paho-mqtt
    python publicador.py              # sequência de ocupações (padrão)
    python publicador.py invalidas    # mensagens inválidas (o ESP32 deve ignorar)
    python publicador.py semdados     # estado "sem dados" e timeout
    python publicador.py manual       # você digita a ocupação em %

Formato da mensagem (sem quebra de linha no MQTT):
    OCUP,<ocupacao_pct>,<nivel>,<alerta>,<valido>
"""

import random
import sys
import threading
import time

import paho.mqtt.client as mqtt

BROKER = "broker.emqx.io"
PORTA = 1883
TOPICO = "dac-teste-2026-ocupacao-74291"  # igual ao do sketch.ino

# Capacidade didática de referência (não é a capacidade real da rede)
CAPACIDADE_REF_BPS = 1_000_000

MENSAGEM_SEM_DADOS = "OCUP,0.0,0,0,0"


def mensagem_por_ocupacao(ocupacao_pct):
    """Monta a mensagem do contrato a partir da ocupação em %."""
    ocupacao = max(0.0, min(100.0, ocupacao_pct))
    # nível e alerta saem do valor SEM arredondar; só o texto é arredondado
    nivel = min(9, int(ocupacao // 10))
    alerta = 1 if ocupacao >= 80 else 0
    return f"OCUP,{ocupacao:.1f},{nivel},{alerta},1"


def montar_mensagem(bytes_total, duracao_s, valido=True):
    """Monta a mensagem a partir de uma janela de captura (será usada na integração)."""
    if not valido:
        return MENSAGEM_SEM_DADOS
    taxa_bps = (bytes_total * 8) / duracao_s
    return mensagem_por_ocupacao(taxa_bps / CAPACIDADE_REF_BPS * 100)


def criar_cliente():
    identificador = f"python-dac-{random.randint(1000, 9999)}"
    try:
        cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=identificador)
    except AttributeError:  # paho-mqtt 1.x
        cliente = mqtt.Client(client_id=identificador)
    cliente.connect(BROKER, PORTA, 60)
    cliente.loop_start()
    return cliente


def publicar(cliente, mensagem):
    cliente.publish(TOPICO, mensagem, qos=0, retain=False)
    print(f"enviado: {mensagem}")


def modo_sequencia(cliente):
    """Cada valor é enviado a cada 1 s durante 5 s."""
    # 79.96 testa o arredondamento: aparece 80.0 no texto, mas continua nível 7 verde
    for ocupacao in [0, 50, 79, 79.96, 80, 90, 100, 0]:
        print(f"\n--- ocupação {ocupacao}% ---")
        for _ in range(5):
            publicar(cliente, mensagem_por_ocupacao(ocupacao))
            time.sleep(1)


def modo_invalidas(cliente):
    """Entre cada mensagem inválida reenvia a válida, para o display ficar em 5."""
    valida = mensagem_por_ocupacao(50)
    invalidas = [
        "OCUP,85.5,8,1",        # faltam campos
        "OCUP,85.5,12,1,1",     # nível fora de 0-9
        "OCUP,85.5,8,0,1",      # alerta incoerente com o nível
        "TRAFEGO,85.5,8,1,1",   # prefixo errado
        "OCUP,85.5,8,1,1,",     # vírgula sobrando
        "OCUP,abc,8,1,1",       # ocupação não numérica
        "abc",                  # lixo
    ]
    print("Esperado: display fixo em 5 (verde); o monitor serial mostra 'Mensagem invalida'")
    for invalida in invalidas:
        publicar(cliente, valida)
        time.sleep(1)
        publicar(cliente, invalida)
        time.sleep(1)
    publicar(cliente, valida)


def modo_semdados(cliente):
    print("\n--- 50% por 3 s ---")
    for _ in range(3):
        publicar(cliente, mensagem_por_ocupacao(50))
        time.sleep(1)
    print("\n--- valido=0 por 2 s (esperado: traço, LEDs apagados) ---")
    for _ in range(2):
        publicar(cliente, MENSAGEM_SEM_DADOS)
        time.sleep(1)
    print("\n--- volta 50% por 2 s ---")
    for _ in range(2):
        publicar(cliente, mensagem_por_ocupacao(50))
        time.sleep(1)
    print("\n--- silêncio por 6 s (esperado: timeout de 3 s e traço) ---")
    time.sleep(6)
    print("\n--- volta 50% ---")
    publicar(cliente, mensagem_por_ocupacao(50))
    time.sleep(1)


def modo_manual(cliente):
    """Reenvia a última mensagem a cada 1 s para o ESP32 não cair em 'sem dados'."""
    estado = {"mensagem": None}

    def reenviar():
        while True:
            if estado["mensagem"]:
                cliente.publish(TOPICO, estado["mensagem"], qos=0, retain=False)
            time.sleep(1)

    threading.Thread(target=reenviar, daemon=True).start()

    while True:
        texto = input("Ocupação em % ('s' = sem dados, 'q' = sair): ").strip().lower()
        if texto == "q":
            break
        if texto == "s":
            estado["mensagem"] = MENSAGEM_SEM_DADOS
        else:
            try:
                estado["mensagem"] = mensagem_por_ocupacao(float(texto.replace(",", ".")))
            except ValueError:
                print("Digite um número, 's' ou 'q'.")
                continue
        print(f"enviando a cada 1 s: {estado['mensagem']}")


MODOS = {
    "sequencia": modo_sequencia,
    "invalidas": modo_invalidas,
    "semdados": modo_semdados,
    "manual": modo_manual,
}


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "sequencia"
    if modo not in MODOS:
        print(f"Modo desconhecido: {modo}. Use: {', '.join(MODOS)}")
        sys.exit(1)

    cliente = criar_cliente()
    print(f"Conectado a {BROKER}, tópico {TOPICO}, modo '{modo}'")
    try:
        MODOS[modo](cliente)
    except KeyboardInterrupt:
        pass
    finally:
        cliente.loop_stop()
        cliente.disconnect()
        print("\nFinalizado.")


if __name__ == "__main__":
    main()