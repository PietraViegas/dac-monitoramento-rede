
import time
import paho.mqtt.client as mqtt

servidor = "broker.emqx.io"
topico = "dac-teste-2026-ocupacao-74291"

cliente = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2
)

cliente.connect(servidor, 1883, 60)
cliente.loop_start()

time.sleep(2)

for numero in range(10):
    print(f"Enviando nivel: {numero}")

    resultado = cliente.publish(topico, str(numero), qos=1)
    resultado.wait_for_publish()

    time.sleep(2)

cliente.loop_stop()
cliente.disconnect()
