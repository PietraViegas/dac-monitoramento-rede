#include <WiFi.h>
#include <PubSubClient.h>

// ===== Configuração (deve ser igual à do publicador Python) =====
const char* servidor = "broker.emqx.io";
const char* topico = "dac-teste-2026-ocupacao-74291";

const unsigned long TEMPO_SEM_DADOS_MS = 3000;  // sem mensagem válida por 3 s = sem dados
const unsigned int TAMANHO_MAX_MENSAGEM = 20;   // contrato: no máximo 20 caracteres

// ===== Pinos (conforme o diagram.json) =====
const int segmentos[7] = {13, 12, 14, 27, 26, 25, 33};  // A, B, C, D, E, F, G
const int PINO_VERDE = 18;
const int PINO_VERMELHO = 19;

// Ordem dos segmentos: A, B, C, D, E, F, G
const byte numeros[10][7] = {
  {1,1,1,1,1,1,0},  // 0
  {0,1,1,0,0,0,0},  // 1
  {1,1,0,1,1,0,1},  // 2
  {1,1,1,1,0,0,1},  // 3
  {0,1,1,0,0,1,1},  // 4 (corrigido: B, C, F, G)
  {1,0,1,1,0,1,1},  // 5
  {1,0,1,1,1,1,1},  // 6
  {1,1,1,0,0,0,0},  // 7
  {1,1,1,1,1,1,1},  // 8
  {1,1,1,1,0,1,1}   // 9
};

// Estado "sem dados": só o segmento G (traço no meio)
const byte traco[7] = {0,0,0,0,0,0,1};

WiFiClient wifi;
PubSubClient mqtt(wifi);

unsigned long ultimaMensagemMs = 0;
bool semDados = true;

// <<INICIO_PARSE
// Interpretação do contrato:  OCUP,<ocupacao_pct>,<nivel>,<alerta>,<valido>

struct Medicao {
  float ocupacao;
  int nivel;
  int alerta;
  int valido;
};

static bool lerInteiro(const char* texto, int minimo, int maximo, int &saida) {
  if (texto == NULL || *texto == '\0') return false;
  char* fim;
  long valor = strtol(texto, &fim, 10);
  if (*fim != '\0') return false;
  if (valor < minimo || valor > maximo) return false;
  saida = (int)valor;
  return true;
}

static bool lerDecimal(const char* texto, float minimo, float maximo, float &saida) {
  if (texto == NULL || *texto == '\0') return false;
  char* fim;
  double valor = strtod(texto, &fim);
  if (*fim != '\0') return false;
  if (!(valor >= minimo && valor <= maximo)) return false;  // também rejeita NaN
  saida = (float)valor;
  return true;
}

bool interpretarMensagem(const char* texto, Medicao &m) {
  size_t tamanho = strlen(texto);
  if (tamanho == 0 || tamanho > 20) return false;

  // Exatamente 4 vírgulas (5 campos), sem campo vazio nem vírgula sobrando
  int virgulas = 0;
  for (size_t i = 0; i < tamanho; i++) {
    if (texto[i] == ',') virgulas++;
  }
  if (virgulas != 4) return false;

  char copia[32];
  strcpy(copia, texto);

  char* campos[5];
  int quantidade = 0;
  char* parte = strtok(copia, ",");
  while (parte != NULL && quantidade < 5) {
    campos[quantidade++] = parte;
    parte = strtok(NULL, ",");
  }
  if (quantidade != 5) return false;

  if (strcmp(campos[0], "OCUP") != 0) return false;
  if (!lerDecimal(campos[1], 0.0, 100.0, m.ocupacao)) return false;
  if (!lerInteiro(campos[2], 0, 9, m.nivel)) return false;
  if (!lerInteiro(campos[3], 0, 1, m.alerta)) return false;
  if (!lerInteiro(campos[4], 0, 1, m.valido)) return false;

  // O alerta precisa ser coerente com o nível (níveis 8 e 9 = alerta).
  // Não comparamos o nível com a ocupação: o Python calcula o nível antes
  // de arredondar a ocupação para 1 casa decimal.
  if (m.alerta != (m.nivel >= 8 ? 1 : 0)) return false;

  return true;
}
// FIM_PARSE>>

void escreverSegmentos(const byte padrao[7]) {
  for (int i = 0; i < 7; i++) {
    digitalWrite(segmentos[i], padrao[i]);
  }
}

void mostrarNivel(int nivel, int alerta) {
  escreverSegmentos(numeros[nivel]);
  digitalWrite(PINO_VERDE, alerta ? LOW : HIGH);
  digitalWrite(PINO_VERMELHO, alerta ? HIGH : LOW);
}

void mostrarSemDados() {
  escreverSegmentos(traco);
  digitalWrite(PINO_VERDE, LOW);
  digitalWrite(PINO_VERMELHO, LOW);
}

void receber(char* topic, byte* payload, unsigned int length) {
  char mensagem[32];

  if (length == 0 || length > TAMANHO_MAX_MENSAGEM) {
    Serial.printf("Mensagem invalida (tamanho %u)\n", length);
    return;
  }

  memcpy(mensagem, payload, length);
  mensagem[length] = '\0';

  Medicao m;
  if (!interpretarMensagem(mensagem, m)) {
    Serial.printf("Mensagem invalida: %s\n", mensagem);
    return;  // mensagem inválida é descartada e não renova o timeout
  }

  ultimaMensagemMs = millis();

  if (!m.valido) {
    semDados = true;
    mostrarSemDados();
    Serial.println("Sem dados (valido=0)");
    return;
  }

  semDados = false;
  mostrarNivel(m.nivel, m.alerta);
  Serial.printf("Recebido: ocup=%.1f nivel=%d alerta=%d\n", m.ocupacao, m.nivel, m.alerta);
}

void conectarMQTT() {
  while (!mqtt.connected()) {
    Serial.println("Conectando ao MQTT...");

    String id = "esp32-dac-" + String(random(100000, 999999));
    if (mqtt.connect(id.c_str())) {
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
  pinMode(PINO_VERDE, OUTPUT);
  pinMode(PINO_VERMELHO, OUTPUT);

  mostrarSemDados();  // começa em "sem dados" até chegar a primeira mensagem

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

  if (!semDados && (millis() - ultimaMensagemMs > TEMPO_SEM_DADOS_MS)) {
    semDados = true;
    mostrarSemDados();
    Serial.println("Sem dados (timeout de 3 s)");
  }
}
