# Teste 3: captura real de tráfego → ocupação → ESP32

Captura pacotes reais da placa de rede com Scapy, calcula a **ocupação da rede** a cada 1 segundo e envia o resultado por MQTT para o ESP32 (Wokwi), que mostra o nível (0 a 9) no display e acende o LED verde ou vermelho.

Diferente do Teste 2, aqui os valores **vêm da rede de verdade**, e não de um script que inventa números.

```
Placa de rede → Scapy (sniffer) → soma por janela de 1 s → ocupação %
                                                              │
                                    MQTT (broker.hivemq.com) ◄┘
                                                │
                                         ESP32 no Wokwi → display 0-9 + LED verde/vermelho
```

## Arquivos

| Arquivo | Função |
|---|---|
| `sniffer_basico.py` | Captura e **imprime** os pacotes (hora, protocolo, tamanho, origem → destino). Também define `extrair_registro()`, usada pelo monitor |
| `monitor.py` | Captura + janela de 1 s + média móvel + envio MQTT. É o programa principal |
| `publicador.py` | **Cópia** do `teste_2/publicador.py`. O monitor importa dele `montar_mensagem()`, o broker e o tópico |
| `calibrar.py` | Mede 3 cenários (normal, vídeo, speedtest) e recomenda a capacidade de referência. Grava `calibracao_resultado.txt` |

Use o `sketch.ino` e o `diagram.json` da pasta `teste_2` (não mudaram).

## Requisitos (Windows)

1. **Npcap** (npcap.com), instalado com a opção "WinPcap API-compatible Mode".
2. `pip install scapy paho-mqtt`
3. Se der erro de permissão ao capturar, abrir o terminal como administrador.

## Como rodar

**Só ver os pacotes (sem MQTT):**

```
python sniffer_basico.py --listar                         # lista as interfaces
python sniffer_basico.py                                  # captura 50 pacotes e mostra o resumo
python sniffer_basico.py --limite 0                       # até Ctrl+C
python sniffer_basico.py --filtro "icmp or icmp6"         # só ping
python sniffer_basico.py --iface "Wi-Fi"                  # escolhe a interface
```

**Monitor completo (com o Wokwi rodando e mostrando `MQTT conectado!`):**

```
python monitor.py                                         # usa o CAPACIDADE_REF_BPS do publicador.py (hoje 20 Mbit/s)
python monitor.py --capacidade 20000000 --media 3         # configuração calibrada: 20 Mbit/s, média de 3 s
python monitor.py --sem-mqtt                              # só mostra as janelas, sem enviar
python monitor.py --duracao 30                            # para sozinho após 30 s
python calibrar.py                                        # refaz a calibração da referência (3 cenários de 30 s)
```

Para parar, **Ctrl+C uma vez só** e esperar "Monitor finalizado". Ao parar, o display do ESP32 volta ao traço ("sem dados").

## O que cada linha do monitor significa

```
19:47:35  TCP  276  UDP    0  ICMP    2  OUTROS    0  |  1096.0 kbit/s | ocupação 100.0% | nível 9 VERMELHO
```

- `TCP/UDP/ICMP/OUTROS`: quantidade de pacotes na janela de 1 s.
- `kbit/s`: taxa (média, se usar `--media`) de TCP + UDP + ICMP. **OUTROS (ex: ARP) não entra na conta.**
- `ocupação`: taxa dividida pela capacidade de referência (`--capacidade`), limitada a 100%.
- `nível`: parte inteira de ocupação/10, máximo 9. Alerta (vermelho) quando a ocupação é **80% ou mais**.

## Regras de medição

- O tamanho de cada pacote é `len(pacote)`: bytes do quadro inteiro, **incluindo cabeçalhos**.
- Conta o tráfego **nos dois sentidos** (o que sai e o que entra).
- Aceita **IPv4 e IPv6**. ICMPv6 conta como ICMP.
- A duração da janela é medida de verdade (não assume 1,000 s).
- O próprio tráfego MQTT do monitor também é capturado (desprezível).

## Formato enviado ao ESP32

```
OCUP,<ocupacao_pct>,<nivel>,<alerta>,<valido>      exemplo: OCUP,85.5,8,1,1
```

Tópico `dac-teste-2026-ocupacao-74291`, QoS 0, sem retain, sem quebra de linha. Detalhes em `teste_2/README.md`.

## Resultados observados

| Teste | Resultado |
|---|---|
| Captura TCP/UDP/ICMP | Funciona. Em 100 pacotes: TCP 91, UDP 5, ICMP 4, OUTROS 0 |
| IPv6 | A 1ª versão classificava IPv6 como OUTROS (41 de 50 pacotes). Corrigido |
| Ping | 1 pedido + 1 resposta por segundo, 74 bytes cada (14 + 20 + 8 + 32) |
| Monitor com tráfego real | 62 s de captura, display e LEDs acompanharam o nível |
| Referência de 1 Mbit/s, sem média | Tráfego normal fica em 10 a 300 kbit/s, mas rajadas chegaram a 14 Mbit/s; o vermelho acendeu em 16 de 62 s |
| Calibração (26/10/2026) | p95 da média móvel: normal 0,63 / vídeo 9,37 Mbit/s; speedtest com mediana de 38,01 Mbit/s. Referência definida em **20 Mbit/s** |
| Monitor com 20 Mbit/s e média de 3 s | O vídeo ficou verde e o speedtest acendeu o vermelho |

## Decisões tomadas

- **Capacidade de referência: 20 Mbit/s, com média móvel de 3 s** (calibração de 26/10/2026; ver `calibracao_resultado.txt` e a decisão D11). Antes o padrão era 1 Mbit/s, e o vermelho acendia em 16 de 62 s em uso normal. A proposta inicial de 10 Mbit/s foi descartada porque o p95 do vídeo (9,37 Mbit/s na média móvel) ocuparia cerca de 94% dela.
- **Vídeo gera rajadas** (o navegador enche um buffer e depois quase para): a média móvel de 3 s resolve, e foi validada com tráfego real.
- **Circuito:** a decodificação do display e o acionamento dos LEDs ficam **por software no ESP32**, via MQTT. O professor aprovou essa escolha por e-mail em 26/10/2026 (justificativa: otimizar o tempo de desenvolvimento e focar na estabilidade da integração). Deve constar em "Tomadas de decisão tecnológica" e na "Justificativa da solução" do PDF (decisão D15).
- **Broker:** desde 25/10/2026 é o `broker.hivemq.com`, porque o `broker.emqx.io` ficou inacessível (ver `registro_incidente_broker_mqtt.txt`). O endereço está em `publicador.py` (`BROKER`) e no `sketch.ino` (`servidor`).

## Ainda não implementado (objetivos da DAC)

Fila dinâmica (buffer) de pacotes, árvore binária de busca ou tabela hash por IP, ordenação do top de consumidores (QuickSort/MergeSort) com análise de complexidade, compressão de logs (Huffman) e relatório consolidado de banda por protocolo.

O circuito com portas lógicas, decodificador e multiplexador **não será feito**: o professor aprovou manter a lógica por software no ESP32.