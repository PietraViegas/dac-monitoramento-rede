# Monitoramento de Tráfego de Rede

Projeto desenvolvido para o DAC, utilizando Python para monitoramento de tráfego de rede e Wokwi para simulação do circuito digital.

## Teste de integração Python + Wokwi

Foi realizado um teste para verificar se seria possível enviar dados automaticamente do Python para o ESP32 simulado no Wokwi.

**Tecnologias utilizadas:**
- Python
- Paho MQTT
- ESP32
- Wokwi
- Broker MQTT público (broker.emqx.io)

### Como funciona?

1. O Python envia números de 0 a 9 utilizando MQTT.
2. O ESP32 simulado no Wokwi recebe esses números.
3. O display de 7 segmentos mostra o número recebido.
4. Os LEDs mudam conforme o valor:
   - **0 a 7:** LED verde aceso.
   - **8 e 9:** LED vermelho aceso.

### Como executar?

**1. Wokwi**

- Abrir o projeto no Wokwi.
- Iniciar a simulação.
- Aguardar a conexão com Wi-Fi e MQTT no monitor serial.

**2. Python**

Instalar as dependências:

```bash
pip install -r requirements.txt
```

Executar o teste:

```bash
python python/teste_integracao.py
```

O Python enviará os números automaticamente e o circuito deverá responder.

## Resultado

A comunicação automática entre Python e Wokwi funcionou corretamente utilizando MQTT.

O teste confirmou que é possível enviar valores do Python e atualizar o display e os LEDs sem intervenção manual.

## Próximos passos

- Implementar a captura de pacotes TCP, UDP e ICMP.
- Implementar fila dinâmica, árvore binária e MergeSort.
- Calcular as métricas de tráfego de rede.
- Adaptar o circuito aos componentes de lógica digital exigidos.
- Substituir os números de teste pelos dados reais processados em Python.

**Status:** teste inicial de integração concluído. O projeto completo ainda está em desenvolvimento.