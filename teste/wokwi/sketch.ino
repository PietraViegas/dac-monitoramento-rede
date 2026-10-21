
#include <WiFi.h>
#include <PubSubClient.h>

const char* servidor = "broker.emqx.io";
const char* topico = "dac-teste-2026-ocupacao-74291";

WiFiClient wifi;
PubSubClient mqtt(wifi);

const int segmentos[7] = {13, 12, 14, 27, 26, 25, 33};

const byte numeros[10][7] = {
  {1,1,1,1,1,1,0},
  {0,1,1,0,0,0,0},
  {1,1,0,1,1,0,1},
  {1,1,1,1,0,0,1},
  {1,0,1,0,0,1,1},
  {1,0,1,1,0,1,1},
  {1,0,1,1,1,1,1},
  {1,1,1,0,0,0,0},
  {1,1,1,1,1,1,1},
  {1,1,1,1,0,1,1}
};

void mostrarNumero(int n) {
  if (n < 0 || n > 9) return;

  for (int i = 0; i < 7; i++) {
    digitalWrite(segmentos[i], numeros[n][i]);
  }

  digitalWrite(18, n < 8);
  digitalWrite(19, n >= 8);
}

void receber(char* topic, byte* payload, unsigned int length) {
  char mensagem[16];

  if (length == 0 || length >= sizeof(mensagem)) return;

  memcpy(mensagem, payload, length);
  mensagem[length] = '\0';

  int numero = atoi(mensagem);

  if (numero >= 0 && numero <= 9) {
    mostrarNumero(numero);
    Serial.printf("Recebido: %d\n", numero);
  }
}

void conectarMQTT() {
  while (!mqtt.connected()) {
    Serial.println("Conectando ao MQTT...");

    if (mqtt.connect("esp32-dac-74291")) {
      mqtt.subscribe(topico);
      Serial.println("MQTT conectado!");
    } else {
      Serial.println("Falha MQTT. Tentando novamente...");
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);

  for (int i = 0; i < 7; i++) {
    pinMode(segmentos[i], OUTPUT);
  }

  pinMode(18, OUTPUT);
  pinMode(19, OUTPUT);

  WiFi.begin("Wokwi-GUEST", "", 6);

  while (WiFi.status() != WL_CONNECTED) {
    delay(200);
  }

  Serial.println("WiFi conectado!");

  mqtt.setServer(servidor, 1883);
  mqtt.setCallback(receber);
  conectarMQTT();
}

void loop() {
  if (!mqtt.connected()) {
    conectarMQTT();
  }

  mqtt.loop();
}
