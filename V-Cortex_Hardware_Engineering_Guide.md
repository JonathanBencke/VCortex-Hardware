# V-Cortex — Guia de Engenharia de Hardware
**Versão:** 1.1
**Data:** 2026-03-24 (revisão técnica: 2026-03-24)
**Autor:** Engenharia de Hardware V-Cortex
**Status:** Rascunho Técnico — Revisão Crítica Aplicada

> **Resumo das alterações v1.0 → v1.1:**
> - **CRÍTICO:** LDO substituído (TLV70033 200mA → AP2112K-3.3 600mA)
> - **CRÍTICO:** MOSFET de proteção substituído (SI2301CDS −20V → SI2359DS −40V)
> - **CRÍTICO:** Buck atualizado (LMR14010 1A → LMR14020 2A) + Power Budget adicionado
> - **CRÍTICO:** Configuração GPS 10Hz adicionada (seção 3.3.4) — UART 115200 baud, protocolo UBX
> - **CRÍTICO:** Inconsistências de nomenclatura corrigidas (TPMP2359DJ, AMS1117, indutor 100µH)
> - **ALTO:** Seção de gerenciamento térmico adicionada (seção 3.5) com análise de dissipação
> - **ALTO:** Restrições mecânicas e form factor documentados (seção 4.6) — PCB 65×45mm
> - **ALTO:** Antena GNSS para caixa fechada — conector U.FL + considerações (seção 3.3.5)
> - **ALTO:** PCB 4 camadas recomendado com stackup definido
> - **ALTO:** Conflito GPIO 33 corrigido no header de expansão
> - **MÉDIO:** CAN TX sem level shifter (direto 3.3V — V_IH TCAN1044V = 2.0V)
> - **MÉDIO:** Decoupling do ESP32 documentado (seção 3.1.3)
> - **MÉDIO:** TVS K-Line substituída por SMD (P6KE24A THT → SMCJ24A SMD)
> - **MÉDIO:** Checklists de testes térmicos, GNSS 10Hz e form factor adicionados

---

## Visão Geral do Sistema

O V-Cortex é um dispositivo embarcado de alta performance para **aquisição de dados e telemetria automotiva/industrial**. Opera em ambientes eletricamente hostis (barramento CAN de veículos, K-Line, alimentação de bateria automotiva) e deve garantir imunidade a transientes, integridade de dados e flexibilidade de protocolo.

### Componentes Principais

| Bloco | Componente | Interface |
|-------|-----------|-----------|
| MCU Principal | ESP32 (Dual Core, 240MHz) | — |
| CAN Transceiver | TCAN1044V | SPI/UART via GPIO |
| K-Line Transceiver | L9637D | UART |
| GNSS | u-blox NEO-M9N | UART + PPS |
| USB-UART | CP2102N | USB Full-Speed |
| MicroSD | Slot padrão | SPI |
| Buck Converter | LMR14010 | — (4–40V → 5V) |
| LDO | AP2112K-3.3 | — (5V → 3.3V) |

---

### Análise de Power Budget

> **CRÍTICO:** O orçamento de corrente deve ser validado antes da escolha final do regulador.

| Subsistema | Típico (mA) | Pico (mA) | Notas |
|------------|------------|-----------|-------|
| ESP32 (CPU ativa) | 100 | 240 | Sem rádio |
| ESP32 (BLE TX) | 130 | 500 | Pico durante anúncio/conexão |
| NEO-M9N GNSS | 25 | 30 | 10Hz, fix adquirido |
| TCAN1044V | 10 | 70 | 70mA durante TX ativo |
| L9637D | 5 | 25 | Depende da carga K-Line |
| CP2102N | 5 | 25 | Durante USB ativo |
| MicroSD (write) | 50 | 150 | Escrita sequencial |
| LED + pull-ups | 10 | 10 | — |
| **TOTAL** | **~335** | **~1050** | **Pico: > 1A** |

**Conclusão:** O LMR14010 (1A) opera **acima do limite** em pico de carga. Usar **LMR14020** (2A, SOT-23-6, mesmo pinout) ou **TPS54202DDCR** (2A, SOT-23-6). A corrente média é segura (~335mA), mas picos de BLE + SD write simultâneos ultrapassam 1A.

**Recomendação para BLE:** Usar modo BLE de baixa potência (advertising interval > 500ms) e bufferizar dados de GNSS para minimizar janelas de TX simultâneo com SD.

---

## 1. Proteção de Entradas — EMI/EMC e Inversão de Polaridade

### 1.1 Entrada V_BATT (9V–16V+, Ambiente Automotivo)

O ambiente automotivo é um dos mais agressivos para eletrônica embarcada. A norma **ISO 7637-2** define os seguintes cenários de transiente que o hardware deve suportar:

| Teste | Descrição | Parâmetros |
|-------|-----------|-----------|
| Pulso 1 | Desconexão de carga indutiva | −75V / 2ms |
| Pulso 2a | Comutação de motor DC | +37V / 0.05ms |
| Pulso 3a/3b | Comutação de ignição | −112V a +75V / µs |
| Pulso 4 | Cranking (partida do motor) | V_BATT cai até 4V / 150ms |
| Pulso 5 (Load Dump) | Desconexão de bateria com alternador ativo | +87V / 400ms |

#### 1.1.1 Proteção Contra Inversão de Polaridade

**Solução recomendada: P-MOSFET em série (lógica ideal)**

```
V_BATT ──┬──[R_G 10kΩ]──┬── GND
         │               │
         └──[GATE P-MOS]──┘
              │
              │ DRAIN → SOURCE → V_BATT_PROT → Buck Converter
```

**Componente recomendado:** **AO3401A** (P-MOSFET, V_DS = −30V, I_D = −4A, R_DS(on) = 50mΩ, SOT-23)
- **Alternativa automotiva:** **DMG3415U** (V_DS = −30V, I_D = −4A, AEC-Q101)
- **Vantagem:** Queda de tensão < 50mV em plena carga (vs. ~0.6V de um diodo Schottky).
- **Operação:** Com polaridade correta, V_GS é negativo → MOSFET conduz. Com inversão, V_GS = 0 → MOSFET bloqueia.

> ⚠️ **CRÍTICO — VDS mínimo:** O TVS SMDJ22A clampeia em 35.5V durante load dump. O MOSFET DEVE ter |V_DS| ≥ 40V para sobreviver. **Não usar SI2301CDS (V_DS = −20V) — será destruído.** Preferir componente com |V_DS| ≥ 40V, ex: **SI2359DS** (V_DS = −40V, I_D = −3.2A, R_DS = 90mΩ, SOT-23).

**Para correntes maiores (> 3A):** usar controlador de diodo ideal **LM74610-Q1** (automotivo, zero queda de tensão de gate).

#### 1.1.2 Proteção contra Transientes (Load Dump e Pulsos ISO 7637)

**Camada 1 — TVS Bidirecional na entrada:**

```
V_BATT_RAW ──[F1 3A polyfuse]──[TVS1]──[LC Filter]── V_BATT_PROT
                                  │
                                 GND
```

**Componente TVS:** SMDJ22A (Unidirecional) ou SMDJ22CA (Bidirecional)
- **Standoff Voltage (Vr):** 22V (Garante não condução durante carga de alternador a 15V ou Jump Start moderado).
- **Clamp Voltage (Vc):** 35.5V @ Peak Pulse Current.
- **Justificativa:** O TVS original de 13V (SMDJ13CA) conduziria durante o carregamento normal da bateria (14.4V), causando falha térmica. O upgrade para 22V exige um Buck Converter que suporte >36V (LMR14010 suporta 40V).
- Polyfuse 3A como proteção de sobrecorrente resetável.

**Camada 2 — Filtro LC de entrada:**

```
V_BATT_PROT ──[L1 10µH]──[C1 100µF/50V]──[C2 100nF]── Buck Input
                              │                │
                             GND              GND
```

- **L1:** IHSM-5832EH100L (10µH, I_sat = 4A, resistência série baixa, núcleo de pó de ferro — alta imunidade a saturação).
- **C1:** Capacitor eletrolítico de baixo ESR, **50V**, 100µF (Tensão nominal aumentada para suportar clamp do TVS).
- **C2:** Cerâmico X7R 100nF/100V (filtragem de alta frequência).

---

### 1.2 CAN-bus — CANH/CANL (TCAN1044V)

O barramento CAN é diferencial e deve suportar tensões de modo comum de −2V a +7V (ISO 11898-2). Em veículos, as linhas podem sofrer acoplamento capacitivo com a ignição e injeção eletrônica.

#### 1.2.1 Proteção ESD e Transientes CAN

```
CANH_EXT ──[R_S 10Ω]──[FB1]──[CANH_IC]── TCAN1044V Pin 7
CANL_EXT ──[R_S 10Ω]──[FB2]──[CANL_IC]── TCAN1044V Pin 6
                          │
                    [TVS_CAN] PESD2CAN
                          │
                         GND
```

**TVS Diferencial CAN:** PESD2CAN (NXP)
- Tensão de clamp: 12V
- Capacitância: 8pF (adequado para CAN FD até 5Mbps — limite prático é C < 30pF)
- Proteção ESD: ±8kV (IEC 61000-4-2, Contato)

**Resistores série:** 10Ω (limitam corrente de pico durante transiente, atenuação < 1dB para CAN 1Mbps).

**Ferrite Beads (FB1, FB2):** BLM21PG601SN1 (Murata)
- Impedância: 600Ω @ 100MHz
- Corrente: 500mA
- Função: Atenua ruído de modo comum de alta frequência sem degradar sinal CAN.

**Common Mode Choke (opcional, recomendado para EMC rigorosa):** ACM2012H-900-2P-T
- Reduz radiação EMI do par CAN em até 20dB.
- Usar entre o conector e os ferrite beads.

#### 1.2.2 Desacoplamento do TCAN1044V

```
VCC (5V) ──[100nF 0402]──[1µF X5R]── Pin VCC do TCAN1044V
                               │
                              GND (via curta, < 1mm)
```

**Pino TXD do ESP32 → TCAN1044V:** conexão **direta é suficiente** — o TCAN1044V especifica V_IH(min) = 2.0V, e o ESP32 fornece 3.3V (margem de 1.3V). Não é necessário level shifter no CAN TX.

**Pino RXD do TCAN1044V → ESP32:** O TCAN1044V opera com VCC = 5V e sua saída RXD pode atingir 5V. O ESP32 possui pinos com tolerância a 5V em GPIOs de entrada (verificar datasheet por GPIO — em geral INPUT_ONLY pins como GPIO34-39 são limitados a 3.6V). **Usar divisor resistivo 10kΩ/20kΩ para proteger a entrada do ESP32.**

> **Simplificação vs. documento anterior:** O 74LVC1T45 para CAN TX foi **eliminado** — desnecessário. Manter 74LVC1T45 apenas para **K-Line TX** (L9637D tem V_IH mais alto e sinal mais lento, justificando o buffer).

---

### 1.3 K-Line / ISO9141 (L9637D)

A linha K é single-wire e opera em modo half-duplex. Em veículos antigos, pode estar sujeita a tensões transitórias de até **+24V** (pico de indução de bobinas de ignição próximas).

#### 1.3.1 Proteção da Linha K

```
K_LINE_EXT ──[R1 100Ω]──[TVS_K]──[K_LINE_IC]── L9637D Pin K
                              │
                         P6KE24A (unidirecional, clamp 24V)
                              │
                             GND
```

**TVS:** P6KE24A
- V_clamp = 33.2V @ 1A (garante proteção contra picos de 24V do barramento)
- Energia: 600W pico
- Unidirecional (linha K só vai positiva em relação ao chassis)

**R1 = 100Ω:** limita corrente de curto-circuito da linha K ao circuito interno.
**C1 = 100nF/50V:** filtro passa-baixa (fc ≈ 16kHz — abaixo da frequência máxima K-Line de ~10.4kbps).

#### 1.3.2 Pull-up da Linha K

O padrão ISO 9141 exige pull-up de **510Ω para V_BATT** (não para 5V). Usar jumper selecionável:

```
V_BATT ──[R_PU 510Ω]──┬── K_LINE_IC
5V     ──[R_PU 1kΩ] ──┘
             │
           [JP_K] (jumper 3 pinos: seleciona V_BATT ou 5V)
```

- **Modo Veículo (padrão):** JP_K em posição V_BATT — compatível ISO9141 e KWP2000.
- **Modo Bancada/Debug:** JP_K em posição 5V — para uso sem bateria automotiva.

---

## 2. Pinagem ESP32 — Validação de Strapping Pins

### 2.1 Strapping Pins Críticos

O ESP32 lê o estado de 5 GPIO durante o reset para determinar o modo de boot. Qualquer sinal externo que force esses pinos para estados incorretos pode impedir o boot ou corromper o flash.

| GPIO | Nome | Estado Correto no Boot | Risco se Errado | Solução |
|------|------|------------------------|-----------------|---------|
| **GPIO 0** | BOOT | **HIGH** = boot normal<br>LOW = modo download | Pull-down externo trava em download mode | Pull-up 10kΩ para 3.3V + botão BOOT para GND |
| **GPIO 2** | — | Não importa (internamente fraco) | Hard HIGH externo pode conflitar com download mode | Usar via resistor 330Ω (LED ou sinal com saída fraca) |
| **GPIO 5** | MTMS | **HIGH** = SDIO timing padrão | Pull-down trava configuração de SDIO | Pull-up 10kΩ para 3.3V — NÃO usar pull-down |
| **GPIO 12** | MTDI | **DEVE ser LOW** = Flash VDD = 3.3V | **Se HIGH: ESP32 tenta alimentar flash com 1.8V → corrompimento ou não boot** | **Pull-down 10kΩ OBRIGATÓRIO** |
| **GPIO 15** | MTDO | HIGH = habilita logs UART0 no boot<br>LOW = silencia logs | — | Pull-up ou pull-down conforme necessidade de debug |

> **ATENÇÃO CRÍTICA — GPIO 12:** Este é o erro mais comum em designs customizados com ESP32. Se qualquer sinal externo forçar GPIO 12 para HIGH durante o boot (ex: MicroSD CS que inicia HIGH, ou sensor com pull-up), o ESP32 seleciona tensão de flash 1.8V. Com flash de 3.3V (que é o padrão dos módulos ESP32), o boot falhará ou o flash será danificado permanentemente. **Sempre use pull-down 10kΩ no GPIO 12.**

### 2.2 Mapeamento Completo de Pinos V-Cortex

```
┌─────────────────────────────────────────────────────────────────┐
│                     ESP32 — PINOUT V-CORTEX                     │
├────────────┬──────────────────────┬────────────────────────────┤
│ GPIO       │ Função V-Cortex      │ Observações                │
├────────────┼──────────────────────┼────────────────────────────┤
│ GPIO 0     │ BOOT Button          │ Pull-up 10kΩ, botão→GND   │
│ GPIO 2     │ LED Status           │ Saída via R 330Ω           │
│ GPIO 4     │ SD_CS                │ Chip Select MicroSD        │
│ GPIO 5     │ CAN_STB              │ Pull-up 10kΩ (HIGH=standby)│
│ GPIO 12    │ LIVRE / ADC          │ PULL-DOWN 10kΩ OBRIGATÓRIO │
│ GPIO 13    │ SD_MOSI              │ SPI MicroSD                │
│ GPIO 14    │ SD_CLK               │ SPI MicroSD                │
│ GPIO 15    │ KLINE_TX             │ Pull-up 10kΩ               │
│ GPIO 16    │ GNSS_RX              │ UART2 RX (recebe de M9N)   │
│ GPIO 17    │ GNSS_TX              │ UART2 TX (envia para M9N)  │
│ GPIO 18    │ CAN_TX               │ Para TCAN1044V via buffer  │
│ GPIO 19    │ CAN_RX               │ Do TCAN1044V               │
│ GPIO 21    │ I2C_SDA              │ Expansão, pull-up 4.7kΩ   │
│ GPIO 22    │ I2C_SCL              │ Expansão, pull-up 4.7kΩ   │
│ GPIO 23    │ SD_MISO              │ SPI MicroSD                │
│ GPIO 25    │ CAN_TERM_CTL         │ Controle terminação CAN    │
│ GPIO 26    │ EXP_GPIO_1           │ Header expansão + ESD      │
│ GPIO 27    │ EXP_GPIO_2           │ Header expansão + ESD      │
│ GPIO 32    │ EXP_GPIO_3           │ Header expansão + ESD      │
│ GPIO 34    │ ADC_VBATT            │ Input only, div. 1:6       │
│ GPIO 35    │ GNSS_PPS             │ Input only, timestamp      │
│ GPIO 36 (VP)│ ADC_EXP_1          │ Input only, expansão       │
│ GPIO 39 (VN)│ ADC_EXP_2          │ Input only, expansão       │
│ TXD0       │ CP2102N_RX           │ UART0 programação/debug    │
│ RXD0       │ CP2102N_TX           │ UART0 programação/debug    │
│ EN         │ Reset via CP2102N    │ Circuito auto-programação  │
├────────────┼──────────────────────┼────────────────────────────┤
│ GPIO 33    │ KLINE_RX             │ Input do L9637D            │
└────────────┴──────────────────────┴────────────────────────────┘
```

### 2.3 Circuito de Auto-Programação (CP2102N → ESP32)

O CP2102N possui pinos DTR e RTS que, com um circuito de dois transistores, permitem programação automática sem pressionar botões físicos.

```
              CP2102N                          ESP32
              ─────────                        ─────────
DTR ──[R1 10kΩ]──┬── BC817-1 ──── GPIO0
                  │    (NPN)
RTS ──[R2 10kΩ]──┼── BC817-2 ──── EN (Reset)
                  │    (NPN)
                 GND

Detalhamento:
  DTR ──[10kΩ]──[BC817 Base]
                [BC817 Emitter]── GND
                [BC817 Collector]──[100nF]──[10kΩ pull-up]── GPIO0

  RTS ──[10kΩ]──[BC817 Base]
                [BC817 Collector]──[100nF]──[10kΩ pull-up]── EN
```

**Sequência de programação automática (esptool.py):**
1. DTR=HIGH, RTS=LOW → GPIO0=LOW, EN=HIGH (modo boot)
2. DTR=LOW, RTS=HIGH → EN=LOW (reset)
3. DTR=LOW, RTS=LOW → EN=HIGH (ESP32 sobe em modo download)

> O capacitor de 100nF cria o pulse necessário no EN sem manter o estado — evita reset contínuo durante comunicação serial normal.

---

## 3. Integridade de Dados — Isolamento de Ruído

### 3.1 Estratégia de Planos de Terra (Ground Planes)

O maior inimigo da integridade de sinal no V-Cortex é o acoplamento entre o Buck Converter (chaveamento a ~1.5MHz) e os circuitos sensíveis (GNSS, ADCs).

#### 3.1.1 Topologia de GND Recomendada: Star Ground

```
                    ┌─── GND_PWR (Buck, Caps de entrada, MOSFET proteção)
                    │
V_BATT GND ─── STAR POINT ─── GND_DIG (ESP32, CP2102N, CAN, MicroSD)
                    │
                    └─── GND_ANA (NEO-M9N, ADCs, filtros analógicos)
                         (conectado ao star point via ferrite bead 600Ω)
```

**Regras de roteamento:**
- O "star point" é o ponto de entrada do capacitor bulk (100µF).
- GND_ANA **nunca** deve ser roteado sob o Buck Converter ou indutor.
- GND_DIG e GND_PWR podem compartilhar plano de cobre, com separação física de componentes.
- Trilhas de retorno de corrente do Buck devem ser curtas e largas (≥ 2mm).

#### 3.1.2 Plano de Cobre e Vias de Stitching

Em PCB de 2 camadas:
- **Layer TOP:** Componentes e trilhas de sinal.
- **Layer BOTTOM:** Plano de cobre GND contínuo (exceto splits necessários).

**Via stitching ao redor do Buck:**
- Grade de vias GND espaçadas a cada 3–5mm ao redor do conversor.
- Impede que correntes de comutação se propaguem pelo plano de GND.

---

#### 3.1.3 Desacoplamento do Módulo ESP32

O ESP32-WROOM-32E possui múltiplos pinos VDD3P3 internos. Embora o módulo tenha decoupling interno, a PCB hospedeira deve fornecer capacitores bulk e bypass adicionais para suprimir picos de corrente durante TX RF.

```
3.3V ──┬── C_BULK1 10µF X5R 0805 (bulk, < 5mm do módulo)
       ├── C_BULK2 10µF X5R 0805 (bulk, lado oposto do módulo)
       ├── C_BYP1  100nF X7R 0402 (< 2mm do módulo, lado do VDD)
       └── C_BYP2  100nF X7R 0402 (< 2mm do módulo, lado oposto)
              │
             GND (via curta, < 1mm para o plano)
```

- Total mínimo: **20µF bulk + 200nF bypass** próximos ao módulo
- Picos de corrente ESP32 BLE TX: ~500mA em < 1µs → capacitores locais são essenciais
- Não conectar estes capacitores "no caminho" do plano — conectar em paralelo direto com trilha de alimentação

---

### 3.2 Buck Converter — LMR14010 (Redução de Ruído de Saída)

O LMR14010 é um conversor Buck que opera a frequência fixa ~1.5MHz. O ripple de saída típico sem filtro adicional é 20–50mVpp — aceitável para lógica digital, mas pode degradar ADCs e o receptor GNSS.

#### 3.2.1 Capacitores de Saída do Buck (5V)

```
V_OUT_5V ──┬── C1 22µF X5R 1206 10V
            ├── C2 22µF X5R 1206 10V
            ├── C3 100nF X7R 0402 10V
            └── C4 10nF X7R 0402 10V
                    │
                   GND
```

A combinação em paralelo garante baixa impedância em toda a faixa 100kHz–100MHz:
- **22µF (×2):** baixa impedância em baixas frequências e frequência de chaveamento.
- **100nF:** transição para média frequência.
- **10nF:** alta frequência (harmônicas do chaveamento).

#### 3.2.2 Indutor do Buck com Blindagem Magnética

**Componente recomendado:** Bourns **SRR1260-4R7Y** (4.7µH, I_sat ≥ 2A) — confirmar valor com cálculo do LMR14010 datasheet para f_sw=1.5MHz e ΔI_L ≤ 30%.
- Núcleo toroidal fechado: fluxo magnético contido, radiação EMI mínima.
- Não usar indutores de núcleo aberto (ex: tipo colonial) — campo disperso acopla em linhas vizinhas.
- **ATENÇÃO:** Indutores de 100µH são inadequados para buck a 1.5MHz — geram ripple de corrente excessivo e aumentam área de PCB desnecessariamente.

#### 3.2.3 Filtro LC Adicional na Saída (5V → LDO AP2112K-3.3)

Para fornecer alimentação mais limpa ao LDO e consequentemente ao ESP32 e GNSS:

```
V_OUT_BUCK_5V ──[L_FILT 10µH]──[C_FILT 10µF]── V_FILTERED_5V ── AP2112K-3.3 Input
                                     │
                                    GND
```

- **L_FILT:** Bourns SRR0604-100Y (10µH, blindado, baixo DCR).
- Atenuação adicional: ~40dB @ 1.5MHz.

**LDO Downstream: AP2112K-3.3TRG1**
- Corrente máxima: **600mA** (vs. 200mA do TLV70033 anterior — inadequado para ESP32)
- Dropout: 250mV @ 600mA (5V − 3.3V = 1.7V de headroom — adequado)
- Pacote: SOT-23-5
- Dissipação máxima: P_LDO = (5V − 3.3V) × 0.4A_típico = **0.68W** — requer via stitching térmico (ver Seção 3.5)
- **Nota:** O TLV70033 (200mA) NÃO deve ser usado — o ESP32 consome até 500mA em pico durante TX BLE, causando brownout.

#### 3.2.4 Posicionamento na PCB

```
┌──────────────────────────────────────────────────────┐
│  PCB V-CORTEX — LAYOUT RECOMENDADO                   │
│                                                       │
│  [CONECTOR V_BATT]                                   │
│  [PROTEÇÃO: MOSFET + TVS + LC]                       │
│  [BUCK LMR14010 + INDUTOR + CAPS]    ← Canto 1       │
│                                                       │
│        [ESP32]  [CP2102N]  [MicroSD]                 │
│                                                       │
│  [CAN: TCAN1044V + Proteção]         ← Borda com OBD │
│  [K-LINE: L9637D + Proteção]         ← Borda com OBD │
│                                                       │
│                          [NEO-M9N]   ← Canto oposto  │
│                          [Antena RF] ← Borda livre    │
└──────────────────────────────────────────────────────┘
```

**Princípio:** GNSS no canto mais distante do Buck Converter. Borda da PCB para a antena (sem metais acima ou abaixo da trilha RF).

---

### 3.3 Módulo GNSS — NEO-M9N

O NEO-M9N opera em 1575.42 MHz (GPS L1) e é extremamente sensível a ruído de RF. O Buck a 1.5MHz possui harmônicas que chegam a 1.5GHz, próximo à banda L1.

#### 3.3.1 Trilha da Antena (50Ω Microstrip)

Para PCB com FR4 padrão (εr ≈ 4.5), espessura de substrato h = 1.6mm, cobre 35µm:

**Largura da trilha para 50Ω:** ≈ **2.9mm** (calcular com Saturn PCB Toolkit para seu stackup específico).

**Regras da trilha RF:**
- Comprimento máximo sem match de impedância: 15mm.
- Nenhuma via, componente ou trilha na zona de exclusão (3mm ao redor da trilha RF).
- Plano de GND contínuo na camada inferior sob toda a trilha RF.
- Não rotear trilhas digitais paralelas à trilha RF.

#### 3.3.2 Desacoplamento de Alimentação do NEO-M9N

```
V_3V3 ──[FB_GNSS 600Ω]──[C1 10µF]──[C2 100nF 0402]──[C3 10nF 0402]── VCC NEO-M9N
                                           │                  │
                                          GND               GND
               C2 e C3: < 0.5mm do pino VCC do módulo (distância é crítica)
```

**Ferrite bead dedicado (FB_GNSS):** isola o VCC do módulo GNSS do restante do plano de 3.3V.

#### 3.3.3 PPS (Pulse Per Second)

O sinal PPS do NEO-M9N é uma saída digital 3.3V com borda de subida precisa (±20ns). Conectar ao GPIO 35 (input only) do ESP32 via resistor série 100Ω (proteção ESD de baixo impacto).

---

#### 3.3.4 Configuração para Taxa de Navegação 10Hz

> **REQUISITO:** O sistema deve operar com atualização GNSS de no mínimo **10Hz** (100ms por ciclo). A configuração padrão do NEO-M9N é 1Hz a 9600 baud — **inadequado para este projeto**.

##### Configuração de Baud Rate

O baud rate padrão (9600) **não comporta** o volume de dados a 10Hz. Cálculo de throughput:

```
Sentenças NMEA a 10Hz (GGA + RMC apenas):
  - GGA: ~80 bytes/sentença × 10Hz = 800 bytes/s
  - RMC: ~70 bytes/sentença × 10Hz = 700 bytes/s
  - Total: ~1500 bytes/s + overhead = ~15000 baud mínimo

Com protocolo UBX binário:
  - NAV-PVT: 100 bytes × 10Hz = 1000 bytes/s → ~10000 baud mínimo

Margem de segurança (×8): usar UART2 a 115200 baud.
```

**Pinout impactado:** GPIO 16 (GNSS_RX) e GPIO 17 (GNSS_TX) — inicializar UART2 a **115200 baud, 8N1**.

##### Sequência de Inicialização (UBX Binary, recomendado)

```c
// 1. Inicializar UART2 a 9600 baud (padrão de fábrica do NEO-M9N)
uart_config_t uart_cfg = {
    .baud_rate = 9600,
    .data_bits = UART_DATA_8_BITS,
    .parity    = UART_PARITY_DISABLE,
    .stop_bits = UART_STOP_BITS_1,
    .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
};
uart_driver_install(UART_NUM_2, 512, 512, 0, NULL, 0);
uart_param_config(UART_NUM_2, &uart_cfg);

// 2. Mudar baud rate do NEO-M9N para 115200 (UBX-CFG-PRT)
uint8_t ubx_set_baud[] = {
    0xB5, 0x62, 0x06, 0x00, 0x14, 0x00,  // UBX-CFG-PRT header
    0x01,                                  // portID = UART1
    0x00, 0x00, 0x00,                      // reserved
    0xC0, 0x08, 0x00, 0x00,               // mode: 8N1
    0x00, 0xC2, 0x01, 0x00,               // baudRate = 115200 (0x0001C200)
    0x07, 0x00,                            // inProtoMask: UBX+NMEA+RTCM
    0x03, 0x00,                            // outProtoMask: UBX+NMEA
    0x00, 0x00, 0x00, 0x00,
    0xBC, 0x5E                             // checksum (calcular via Fletcher)
};
uart_write_bytes(UART_NUM_2, ubx_set_baud, sizeof(ubx_set_baud));
vTaskDelay(pdMS_TO_TICKS(100));

// 3. Reconfigurar UART2 do ESP32 para 115200
uart_set_baudrate(UART_NUM_2, 115200);

// 4. Configurar taxa de navegação para 10Hz (UBX-CFG-RATE)
uint8_t ubx_set_rate[] = {
    0xB5, 0x62, 0x06, 0x08, 0x06, 0x00,  // UBX-CFG-RATE header
    0x64, 0x00,                            // measRate = 100ms (10Hz)
    0x01, 0x00,                            // navRate = 1 (solução por medição)
    0x01, 0x00,                            // timeRef = GPS
    0x7A, 0x12                             // checksum
};
uart_write_bytes(UART_NUM_2, ubx_set_rate, sizeof(ubx_set_rate));
vTaskDelay(pdMS_TO_TICKS(100));

// 5. Desabilitar todas as mensagens NMEA, habilitar apenas NAV-PVT (mais eficiente)
// UBX-NAV-PVT: posição, velocidade e tempo em um único pacote de 92 bytes
uint8_t ubx_enable_navpvt[] = {
    0xB5, 0x62, 0x06, 0x01, 0x03, 0x00,  // UBX-CFG-MSG
    0x01, 0x07,                            // msgClass=NAV, msgID=PVT
    0x01,                                  // rate = 1 (a cada solução)
    0x13, 0x51                             // checksum
};
uart_write_bytes(UART_NUM_2, ubx_enable_navpvt, sizeof(ubx_enable_navpvt));
```

> **NOTA:** Os checksums UBX nos exemplos acima são ilustrativos. Calcular o checksum real com o algoritmo Fletcher-8 (soma de todos bytes do payload). Usar biblioteca como `ubxlib` ou calcular manualmente.

##### Configuração do PPS a 10Hz

Por padrão, o PPS pulsa a 1Hz. Para sincronização de timestamp a 10Hz, configurar via UBX-CFG-TP5:

```c
// UBX-CFG-TP5: Time Pulse 5 — configurar PPS para 10Hz
// timePulseFreq = 10Hz, pulseLenRatio = 10% duty cycle
// (enviar payload completo de 32 bytes — consultar NEO-M9N Integration Manual)
```

Alternativamente, usar o próprio timestamp da mensagem NAV-PVT (campo `iTOW` com resolução de 1ms) para sincronização de dados — eliminando a necessidade de PPS a 10Hz.

##### Verificação de Throughput

| Configuração | Taxa (baud) | Carga UART (%) | Status |
|---|---|---|---|
| NMEA 1Hz, 9600 baud | 9600 | ~15% | OK (padrão de fábrica) |
| NMEA 10Hz, 9600 baud | 9600 | **~150%** | **FALHA — overflow** |
| NMEA 10Hz, 115200 baud | 115200 | ~13% | OK |
| UBX NAV-PVT 10Hz, 115200 baud | 115200 | ~9% | **Ideal** |

---

#### 3.3.5 Antena GNSS para Caixa Fechada (OBD2 Box)

> **PROBLEMA:** O V-Cortex opera dentro de uma caixa fechada conectada à porta OBD2, geralmente sob o painel do carro. Esta posição implica:
> - Plástico da caixa: atenuação de 3–10 dB no sinal GPS L1 (1575.42 MHz)
> - Metal do painel/carro: potencial bloqueio completo (faraday cage parcial)
> - Localização sub-ótima: carro bloqueia ~50% do hemisfério de visão do céu

**Solução recomendada: Conector U.FL para antena ativa externa**

```
NEO-M9N RF_IN ──[trilha 50Ω < 10mm]──[U.FL Connector]──── Cabo coaxial (max 1m) ──── Antena ativa externa
                                                                                        (presa no pára-brisa
                                                                                         ou teto interno)
```

**Antena ativa externa recomendada:**
- Tipo: Patch ativa com LNA integrado, ganho ≥ 26dB
- Alimentação: 3.3V via bias-T (NEO-M9N fornece V_ANT em pino dedicado)
- Conector: SMA fêmea externo + cabo U.FL → SMA, comprimento ≤ 1m

**Bias-T para antena ativa:**
```
V_ANT (NEO-M9N) ──[L_BIAS 47nH]──┬── U.FL (sinal RF + DC bias)
                                   │
                               [C_BLOCK 100pF]── RF_IN do NEO-M9N
```
O NEO-M9N possui controle de corrente de antena integrado com detecção de curto-circuito.

**Se antena interna for utilizada (patch 25×25mm):**
- Material da caixa: ABS ou PC **sem** metalização, sem pigmentos de carbono
- Posicionar patch no topo da caixa, o mais próximo possível do teto/pára-brisa
- Garantir zona livre de metal (distância ≥ 10mm) ao redor da antena
- Atenuação esperada pelo plástico: aceitar sensibilidade reduzida (−6 dB mínimo)

**Atualização do Layout (canto do GNSS):**
```
┌──────────────────────────────────────────────────────┐
│  [U.FL Conector]  ← borda da PCB, área sem silkscreen│
│  [NEO-M9N]       ← trilha RF < 10mm ao conector      │
│  Exclusion zone  ← 3mm ao redor da trilha RF         │
└──────────────────────────────────────────────────────┘
```

---

### 3.4 Linhas CAN Diferenciais — Roteamento em PCB

```
Impedância diferencial CAN: 120Ω (ISO 11898-2)
Configuração para FR4 1.6mm, 2 camadas:

  ┌────────────────────────────────────────┐
  │  W = 0.20mm   Gap = 0.20mm            │
  │  ══════════  ══════════               │
  │   CANH           CANL                 │
  │  (TOP layer, plano GND na BOTTOM)     │
  └────────────────────────────────────────┘
```

**Regras de roteamento CAN:**
- Manter par diferencial com espaçamento constante (< 0.5mm de variação).
- Distância mínima de 3mm de trilhas de clock (SPI, SDIO) e Buck.
- Não cruzar trilhas de alta frequência na camada oposta sob o par CAN.
- Comprimento máximo sem terminação: 40m @ 1Mbps; 1m @ 5Mbps (CAN FD).

---

### 3.5 Gerenciamento Térmico — Caixa OBD2 Fechada

> **CONTEXTO CRÍTICO:** O V-Cortex opera em uma caixa plástica **completamente fechada** conectada à porta OBD2. Não há ventilação forçada. A temperatura ambiente na cabine pode atingir **60–85°C** (plataforma sob o painel em dias quentes). A gestão térmica não é opcional — é condição de sobrevivência do hardware.

#### 3.5.1 Budget de Dissipação Térmica

| Componente | Condição | Potência Dissipada |
|-----------|----------|-------------------|
| LMR14010 (Buck) | V_IN=12V, V_OUT=5V, I=0.4A, η=85% | **(12−5) × 0.4 × 0.15 ≈ 0.42W** |
| AP2112K-3.3 (LDO) | V_IN=5V, V_OUT=3.3V, I=0.4A | **(5−3.3) × 0.4 = 0.68W** |
| ESP32 (processamento) | Dual core ativo, sem rádio | ~0.4W |
| ESP32 (BLE TX) | Pico curto | ~0.8W (transitório) |
| TCAN1044V | TX ativo | ~0.1W |
| **TOTAL (típico)** | — | **~1.6W contínuo** |
| **TOTAL (pico)** | — | **~2.4W (transitório)** |

**Temperatura de junção estimada (sem dissipador):**
```
T_junction = T_ambient + P × θ_ja

LDO AP2112K (SOT-23-5, θ_ja = 250°C/W):
  T_j = 80°C + 0.68W × 250°C/W = 80 + 170 = 250°C → DESTRUIÇÃO

LDO AP2112K (SOT-23-5, com copper pour 1cm²):
  θ_ja_efetivo ≈ 120°C/W
  T_j = 80°C + 0.68W × 120°C/W = 80 + 82 = 162°C → ainda crítico

→ SOLUÇÃO: eliminar LDO ou usar topologia mais eficiente (ver 3.5.3)
```

#### 3.5.2 Estratégias de Mitigação Térmica na PCB

**1. Thermal Vias sob Buck e LDO:**
```
TOP: Pad thermal do componente
      │││
     Vias (grade 0.3mm drill, 0.6mm pad, espaçamento 1.2mm)
      │││
BOTTOM: Copper pour GND (mínimo 4cm²)
```
- Grade de vias de calor (thermal vias): pelo menos 9 vias sob cada componente de potência.
- Conectar ao plano de GND no bottom layer para distribuição de calor.

**2. Copper Pour como Heatsink:**
- Área mínima de copper pour no bottom layer: **4cm²** sob/ao redor do buck e LDO.
- Remover máscara de solda (solder mask opening) sobre a área do pour para maximizar convecção.

**3. Especificação de Caixa:**
- Material: **ABS** com temperatura de serviço contínuo ≥ 80°C (ex: ABS Novodur P2H, Tg = 105°C).
- Não usar PLA (Tg ≈ 60°C) ou borracha termoplástica.
- Se possível, usar caixa com nervuras internas de alumínio como dissipador passivo.

#### 3.5.3 Topologia Alternativa: Buck Duplo (Recomendado para Produção)

A maior fonte de dissipação é o LDO: converte 5V→3.3V com eficiência de apenas **66%**. Alternativa:

```
V_BATT ──[Buck_1: LMR14010]── 5V  ──► TCAN1044V, L9637D, CP2102N
         (η ≈ 85%)
V_BATT ──[Buck_2: LMR14010]── 3.3V ──► ESP32, NEO-M9N
         (η ≈ 87%)
```
- Elimina o LDO completamente → reduz dissipação total em **~0.68W**
- Custo adicional: ~$0.50/unidade (segundo LMR14010)
- Filtro LC adicional de 10µH na saída do Buck_2 para limpar ruído antes do ESP32/GNSS

#### 3.5.4 Monitoramento de Temperatura

Adicionar um **NTC 10kΩ B=3950** conectado ao GPIO 36 (ADC) como sensor de temperatura interna da caixa:

```
3.3V ──[R_ref 10kΩ]──┬── GPIO 36 (ADC)
                      │
                    [NTC 10kΩ]
                      │
                     GND

T(°C) = 1 / (ln(R_ntc/10000)/3950 + 1/298.15) - 273.15
```

- Firmware deve registrar temperatura junto com dados GNSS/CAN.
- Implementar throttling: reduzir frequência de BLE/SD se T > 70°C.

---

## 4. Flexibilidade de Hardware

### 4.1 Resistor de Terminação CAN Selecionável por Software

Em redes CAN, apenas os dois nós nas **extremidades** da rede precisam de resistor de terminação de 120Ω. Se o V-Cortex for colocado no meio da rede (ex: como gateway), a terminação deve ser desabilitada.

#### 4.1.1 Terminação Controlada por GPIO (Solução Recomendada)

```
CANH ──┬─────────────────────────┬── CANL
       │                         │
      [R_T1 60Ω]            [R_T2 60Ω]
       │                         │
       └──[BSS138 Drain]──[BSS138 Drain]──┘ (dois MOSFETs em série para robustez)
           [BSS138 Gate] ←── GPIO 25 (ESP32) via [R_G 10kΩ]
           [BSS138 Source]── GND
```

**Simplificado (solução mais comum):**
```
CANH ──[R_TERM 120Ω]──[BSS138]── CANL
                         │
                       GPIO 25 (via 10kΩ)
```

**Componente:** BSS138 (N-MOSFET, V_GS(th) = 0.8–1.5V, compatível com 3.3V do ESP32)

**Controle por firmware:**
```c
// Ativar terminação (nó de extremidade da rede CAN)
gpio_set_level(GPIO_CAN_TERM, 1);

// Desativar terminação (nó intermediário da rede CAN)
gpio_set_level(GPIO_CAN_TERM, 0);
```

#### 4.1.2 Alternativa: Jumper de Solda (Hardware Fixo)

Para versões de baixo custo sem controle por software:
```
CANH ──[R_TERM 120Ω]──[PAD_A]──[PAD_B]── CANL
                       ↑
              Soldar 0Ω para habilitar terminação
```
- Footprint 0402 com dois pads.
- Documentar claramente na silkscreen: "JP_TERM: Soldar = nó de extremidade".

---

### 4.2 Pull-ups K-Line Selecionáveis

#### 4.2.1 Jumper de 3 Posições

```
                    ┌─ [R_PU1 510Ω] ─── V_BATT (padrão ISO9141)
K_LINE_IC ──────────┤
                    └─ [R_PU2 1kΩ] ──── V_5V (modo bancada/debug)

Implementação com jumper físico:
    PIN1 (V_BATT) ─── JP1 ─── PIN2 (K_LINE) ─── JP1 ─── PIN3 (V_5V)

    Jumper em PIN1-PIN2: pull-up para V_BATT (modo veículo)
    Jumper em PIN2-PIN3: pull-up para 5V (modo bancada)
```

#### 4.2.2 Alimentação do L9637D

O L9637D requer VCC entre 4.5V e 28V. No V-Cortex:
- VCC do L9637D = 5V (saída do Buck) para operação normal.
- Pino de alimentação com capacitor de desacoplamento 10µF + 100nF.
- **Não** alimentar diretamente de V_BATT — garante regulação independente.

---

### 4.3 Conversão de Nível de Tensão (3.3V ESP32 ↔ 5V Periféricos)

O ESP32 opera em 3.3V, mas o TCAN1044V e L9637D requerem entradas lógicas de 5V.

#### 4.3.1 Saídas do ESP32 para Periféricos 5V (Unidirecional)

**Solução 1 — Divisor Resistivo (simples, para sinais lentos):**
```
GPIO_ESP32 (3.3V) ──[R1 10kΩ]──[R2 20kΩ]── GND
                              │
                          PERIFÉRICO 5V Input
                    (V_out = 3.3V × 20k/(10k+20k) = 2.2V — FALHA)
```
> Esta abordagem NÃO funciona para subir de 3.3V para 5V. É usada apenas para descer de 5V para 3.3V.

**Solução 2 — Buffer 74LVC1T45 (recomendado para CAN TX e KLINE TX):**
```
VCCA (3.3V) ── [74LVC1T45] ── VCCB (5V)
GPIO_ESP32 → A               B → TCAN1044V / L9637D
```
- Propagation delay: 4.5ns (adequado para CAN FD 5Mbps).
- Pacote SOT23-6, 6 pinos.
- Custo: ~$0.15/unidade.

**Alternativa:** MOSFET N-channel BSS138 com pull-up 10kΩ para 5V (open-drain level shifter). Adequado para sinais lentos (K-Line ≤ 10.4kbps).

#### 4.3.2 Entradas do ESP32 (5V → 3.3V)

**Divisor resistivo** (simples, baixo custo):
```
SINAL_5V ──[R1 10kΩ]──┬── GPIO_ESP32
                       │
                    [R2 20kΩ]
                       │
                      GND
V_GPIO = 5V × 20k/(10k+20k) = 3.33V ✓
```
Adequado para: CAN RX, KLINE RX, sinais digitais de baixa velocidade.

Para alta velocidade (CAN FD): usar 74LVC1T45 bidirecional.

---

### 4.4 Headers de Expansão

#### 4.4.1 Header I2C (4 pinos)

```
J_I2C (2.54mm):
  Pin 1: GND
  Pin 2: 3.3V (máx 200mA via LDO)
  Pin 3: SDA (GPIO 21, pull-up 4.7kΩ)
  Pin 4: SCL (GPIO 22, pull-up 4.7kΩ)
```

Resistores pull-up I2C em footprint 0402: instalar apenas se não houver pull-ups no dispositivo escravo. Adicionar pad de corte (jumper SMD 0Ω) para desabilitar.

#### 4.4.2 Header SPI (6 pinos)

```
J_SPI (2.54mm):
  Pin 1: GND
  Pin 2: 3.3V
  Pin 3: MOSI (GPIO 13)
  Pin 4: MISO (GPIO 23)
  Pin 5: SCK (GPIO 14)
  Pin 6: CS_EXP (GPIO 27)
```

Nota: MicroSD usa o mesmo barramento SPI. CS separado por GPIO garante sem conflito de seleção.

> ⚠️ **Atenção para logging GNSS 10Hz:** O barramento SPI é compartilhado entre MicroSD e o header de expansão. Operações de escrita no SD card podem bloquear o barramento por 10–50ms dependendo do cartão. A 10Hz (100ms/frame), isso representa 10–50% do ciclo de logging. **Firmware DEVE usar mutex/semáforo** para serializar o acesso ao SPI. Avaliar uso de DMA SPI para reduzir overhead de CPU durante escritas.

#### 4.4.3 Header GPIO de Expansão (6 pinos)

```
J_GPIO (2.54mm):
  Pin 1: GND
  Pin 2: 3.3V
  Pin 3: GPIO 26 (+ proteção ESD PRTR5V0U2X)
  Pin 4: GPIO 32 (+ proteção ESD)
  Pin 5: GPIO 36/VP (ADC input only, + proteção ESD)   ← era GPIO 33 (CONFLITO: 33 = KLINE_RX)
  Pin 6: GPIO 34 (ADC input only, divisor 1:2 opcional)
```

**ESD em cada GPIO do header:** PRTR5V0U2X (NXP)
- 2 canais por pacote SOT363
- Clamp 5.5V, capacitância 0.5pF
- Previne danos por conexão de cabos em campo

---

### 4.5 Monitor de Tensão V_BATT (ADC)

O ESP32 ADC tem resolução de 12 bits (0–3.3V). Para medir V_BATT (9–16V):

```
V_BATT ──[R1 100kΩ]──┬── GPIO 34 (ADC)
                      │
                   [R2 22kΩ]
                      │
                     GND

V_ADC = V_BATT × 22k/(100k+22k) = V_BATT × 0.18

Escala: 16V → 2.88V (dentro da faixa ADC de 3.3V) ✓
        9V  → 1.62V ✓

Calibração firmware:
float vbatt = adc_read_mv(GPIO34) / 0.18;
```

**Capacitor de filtro:** 100nF entre o ponto de divisão e GND (reduz ruído de amostragem do ADC).

---

## 4.6 Restrições Mecânicas — Form Factor OBD2

### 4.6.1 Dimensões Alvo

| Parâmetro | Especificação | Justificativa |
|-----------|--------------|---------------|
| PCB footprint | **65 × 45mm máximo** | Caixa OBD2 típica: 70×50×25mm |
| Altura máxima de componentes | **10mm** (lado de cima) | Folga para tampa da caixa |
| Altura máxima (lado de baixo) | **2mm** (SMD apenas) | Clearance para conector OBD2 |
| Conector OBD2 | Pinos THT aceitos | Resistência mecânica necessária |

### 4.6.2 Substituições de Componentes por Form Factor

Os componentes abaixo são incompatíveis com caixa OBD2 e devem ser substituídos:

| Componente Original | Pacote | Problema | Substituto |
|---------------------|--------|----------|-----------|
| P6KE24A (TVS K-Line) | DO-204 (THT) | Through-hole, altura ~15mm | **SMCJ24A** (SMC/DO-214AB, SMD) |
| C1 100µF/50V (Bulk) | SMD D8 (eletrolítico) | Altura 8mm, pode ser mais baixo | **GRM32ER61H107** (MLCC 100µF/50V) ou polymer cap 6.3mm height |
| Headers 2.54mm (I2C, SPI, GPIO) | PTH 2.54mm | Muito altos para caixa fechada | **Test pads** ou conector **Molex PicoBlade 1.25mm** |
| CR1220 Coin Cell Holder | SMD | Altura ~5mm | **Supercapacitor 0.1F/5.5V** (Seiko CPX3225A) para backup GNSS curto prazo, ou eliminar e usar cold-start |

### 4.6.3 PCB — Aviso sobre Número de Camadas

> ⚠️ **RECOMENDAÇÃO FORTE: PCB de 4 camadas**

A combinação de requisitos deste projeto é incompatível com PCB de 2 camadas de alta qualidade:

| Requisito | 2 Camadas | 4 Camadas |
|-----------|-----------|-----------|
| Ground plane contínuo sob GNSS microstrip 50Ω | Impossível com roteamento denso | Camada 2 dedicada a GND |
| Star ground sem fragmentar plano de GND | Contradição intrínseca | Plano GND na camada 2 intocado |
| Isolamento Buck ↔ GNSS | Compromisso severo | Camada Power separada |
| CAN 120Ω diferencial | Difícil de manter | Controlado com precisão |

**Stackup recomendado (4 camadas, 1.6mm total):**
```
Layer 1 (TOP):    Componentes + trilhas de sinal + RF
Layer 2:          GND sólido (não fragmentar — nunca rotear sinais aqui)
Layer 3:          Power planes (5V, 3.3V)
Layer 4 (BOTTOM): Trilhas de retorno + copper pour GND adicional
```

**Se 2 camadas for mandatório por custo:**
- Aceitar que a trilha GNSS RF não terá impedância controlada (manter < 10mm)
- Usar island ground em vez de star ground (ground flood no top + bottom com via stitching)
- Documentar a degradação esperada de −3 a −6 dB na sensibilidade GNSS

---

## 5. Diagrama de Blocos do Sistema

```
                        ┌─────────────────────────────────────┐
                        │          V-CORTEX HARDWARE          │
                        │                                     │
V_BATT (9-16V) ─────────►  [PROTEÇÃO]     [BUCK LMR14010]    │
  │                     │  P-MOSFET      5V ──► [AP2112K-3.3]│
  │                     │  TVS SMDJ22A        3.3V ──► ESP32 │
  │                     │  LC Filter          3.3V ──► M9N   │
  │                     │                                     │
CANH/CANL ──────────────►  [TVS PESD2CAN]                    │
  (ISO 11898-2)         │  [CMC + Ferrites]  ► TCAN1044V     │
                        │                    ► ESP32 GPIO18/19│
                        │                                     │
K-LINE ─────────────────►  [TVS P6KE24A]                     │
  (ISO 9141)            │  [R série 100Ω]    ► L9637D        │
                        │  [Pull-up JP]      ► ESP32 GPIO15/33│
                        │                                     │
USB ────────────────────►  [CP2102N]         ► ESP32 UART0   │
  (Prog/Debug)          │  [Auto-prog NPN]   ► GPIO0, EN     │
                        │                                     │
Antena GNSS ────────────►  [50Ω microstrip]  ► NEO-M9N       │
                        │                    ► ESP32 UART2   │
                        │                    ► GPIO35 (PPS)  │
                        │                                     │
MicroSD ────────────────►  [Slot + ESD]      ► ESP32 SPI     │
                        │                    GPIO 4/13/14/23  │
                        │                                     │
Header I2C/SPI/GPIO ─────►  [ESD PRTR5V0U2X] ► Expansão     │
                        └─────────────────────────────────────┘
```

---

## 6. Lista de Materiais (BOM) — Componentes de Proteção e Flexibilidade

> **REQUISITO DE TEMPERATURA:** Todos os componentes devem ser rated para **−40°C a +85°C** (automotivo under-dash). Verificar datasheet antes de substituições.

| Ref | Componente | Valor/Parte | Pacote | Qtd | Função | Temp Range |
|-----|-----------|-------------|--------|-----|--------|-----------|
| Q1 | **SI2359DS** | P-MOSFET, V_DS=**−40V**, I_D=−3.2A, R_DS=90mΩ | SOT-23 | 1 | Proteção inversão V_BATT | −55 a +150°C |
| F1 | Polyfuse | 3A/30V | SMD 1812 | 1 | Sobrecorrente V_BATT | −40 a +85°C |
| TVS1 | SMDJ22A | 22V/1500W | SMC | 1 | Load dump V_BATT | −55 a +150°C |
| L1 | IHSM-5832EH100L | 10µH/4A | IHSM5832 | 1 | Filtro entrada Buck | −40 a +125°C |
| C1 | Polymer Cap | 100µF/50V low-profile | SMD | 1 | Bulk entrada (**substituiu eletrolítico THT**) | −55 a +105°C |
| U_BUCK | **LMR14020** | 40V/**2A**, Step-down | SOT-23-6 | 1 | DC/DC Step-down (**upgrade de 1A→2A**) | −40 a +125°C |
| U_LDO | **AP2112K-3.3TRG1** | 3.3V/**600mA** | SOT-23-5 | 1 | LDO Linear (**substituiu TLV70033 200mA**) | −40 a +125°C |
| TVS2 | PESD2CAN | CAN TVS | SOT-363 | 1 | Proteção CANH/CANL | −40 a +125°C |
| FB1,FB2 | BLM21PG601SN1 | 600Ω@100MHz | 0805 | 2 | EMI CAN | −40 a +85°C |
| CMC1 | ACM2012H-900-2P-T | Common mode choke | 2012 | 1 | EMC CAN | −40 a +85°C |
| TVS3 | **SMCJ24A** | 24V/1500W | SMC | 1 | Proteção K-Line (**substituiu P6KE24A DO-204 THT**) | −55 a +150°C |
| R_K | — | 100Ω | 0402 | 1 | Série K-Line | −55 a +155°C |
| Q2,Q3 | BC817 | NPN BJT | SOT-23 | 2 | Auto-prog CP2102N | −65 a +150°C |
| R_TERM | — | 120Ω/1% | 0402 | 1 | Terminação CAN | −55 a +155°C |
| Q4 | BSS138 | N-MOSFET | SOT-23 | 1 | Chave terminação CAN | −55 a +150°C |
| U_LS1 | 74LVC1T45 | Level shifter 3.3V↔5V | SOT23-6 | 1 | K-Line TX apenas (**CAN TX não precisa de level shift**) | −40 a +85°C |
| ESD1-4 | PRTR5V0U2X | ESD 5.5V | SOT363 | 2 | Proteção headers GPIO | −40 a +125°C |
| FB_GNSS | BLM21PG601SN1 | 600Ω@100MHz | 0805 | 1 | Isolamento GNSS VCC | −40 a +85°C |
| L_FILT | SRR0604-100Y | 10µH | SRR0604 | 1 | Filtro pós-Buck | −40 a +125°C |
| BAT1 | **Seiko CPX3225A** | Supercap 0.1F/5.5V | SMD | 1 | Backup GNSS (**substituiu CR1220 para low-profile**) | −20 a +70°C |
| J_ANT | U.FL Connector | 50Ω, SMD | U.FL | 1 | Conector antena GNSS externa | −40 a +85°C |
| NTC1 | NTC 10kΩ B=3950 | Termistor | 0402 | 1 | Monitoramento temperatura interna | −40 a +125°C |

---

## 7. Checklist de Validação e Testes

### 7.1 Testes de Bancada (Antes do Primeiro Boot)

- [ ] Medir continuidade entre V_BATT e GND antes de energizar (verificar curto-circuito)
- [ ] Medir tensão em V_BATT_PROT com V_BATT nominal (12V) → deve ser ~12V (sem queda significativa)
- [ ] Aplicar −12V em V_BATT por 5 segundos → verificar 0V em V_BATT_PROT (MOSFET bloqueou)
- [ ] Medir V_BUCK_OUT → deve ser 5.0V ± 2%
- [ ] Medir V_LDO_OUT → deve ser 3.3V ± 2%
- [ ] Medir ripple em V_LDO_OUT com osciloscópio (sonda ×10, BW limit OFF) → deve ser < 30mVpp

### 7.2 Testes de Boot ESP32

- [ ] ESP32 inicializa e exibe mensagens no terminal serial (115200 baud)
- [ ] GPIO 12 medido como LOW com voltímetro (pull-down funcionando)
- [ ] Pressionar BOOT + RST: ESP32 entra em download mode (esptool.py detecta)
- [ ] Programação via USB (sem pressionar botões) funciona (auto-prog CP2102N)
- [ ] Verificar que GPIO 5 (CAN_STB) está HIGH no boot → TCAN1044V em standby

### 7.3 Testes de Comunicação

- [ ] CAN: Enviar e receber frame CAN 2.0B a 500kbps com analisador CAN externo
- [ ] CAN FD: Testar a 2Mbps data phase (se suportado pelo firmware)
- [ ] K-Line: Comunicação ISO9141 com emulador ELM327 ou veículo real
- [ ] GNSS: NEO-M9N adquire fix em < 60s em campo aberto; PPS visível no GPIO 35
- [ ] **GNSS 10Hz:** Confirmar recepção de mensagens UBX NAV-PVT a 100ms de intervalo (log de timestamps mostra delta = 100 ± 5ms)
- [ ] **GNSS 10Hz via UART:** Confirmar que UART2 opera a 115200 baud sem overflow (sem perda de pacotes UBX)
- [ ] MicroSD: Gravar/ler arquivo de 1MB sem erros (teste com `sdtest` do ESP-IDF)
- [ ] **MicroSD @ 10Hz:** Gravar 60 segundos de dados NAV-PVT a 10Hz (~60KB) e verificar integridade sem perda de frames
- [ ] USB: CP2102N enumerado corretamente no SO host

### 7.4 Testes de EMC/EMI (Básicos)

- [ ] Ruído ripple no rail 3.3V: < 50mVpp com Buck em plena carga
- [ ] GNSS não perde fix quando CAN está transmitindo a 1Mbps
- [ ] Simular transiente Load Dump (pulso 24V/50ms em V_BATT via gerador de função + resistor série): circuito sobrevive sem dano
- [ ] Medir tensão de clamp do TVS1 durante transiente (deve ser < 20V no ponto protegido)

### 7.6 Testes Térmicos (Caixa Fechada)

- [ ] Operar o V-Cortex em caixa fechada por 30 minutos com GNSS 10Hz + CAN 500kbps + SD logging
- [ ] Medir temperatura da caixa com termopar externo: deve ser < 65°C em ambiente de 25°C
- [ ] Medir temperatura de junção estimada (via NTC interno): deve ser < 85°C
- [ ] Testar brownout: reduzir V_BATT para 9V (mínimo) → ESP32 não deve reiniciar
- [ ] Testar brownout detector: configurar limiar em 2.43V e verificar que reset ocorre antes de comportamento indefinido
- [ ] Verificar que firmware implementa throttling ao atingir T > 70°C (reduz BLE advertising)

### 7.7 Validação de Form Factor

- [ ] PCB cabe na caixa OBD2 com folga mínima de 1mm em todas as direções
- [ ] Nenhum componente ultrapassa altura de 10mm (verificar com paquímetro)
- [ ] Conector OBD2 alinha corretamente com abertura da caixa
- [ ] Tampa da caixa fecha sem pressionar componentes
- [ ] Conector U.FL acessível para cabo de antena (abertura na caixa ou roteamento interno)

### 7.5 Verificação de Terminação CAN

```c
// Teste firmware — verificar terminação ativável por software:
gpio_set_level(GPIO_CAN_TERM, 1); // Liga
// Medir resistência entre CANH e CANL com multímetro: deve ser ~120Ω
gpio_set_level(GPIO_CAN_TERM, 0); // Desliga
// Medir novamente: deve ser > 10kΩ (linha flutuante)
```

---

## 8. Próximos Passos — Desenvolvimento

1. **Schematic Review:** Validar este guia com ferramenta EDA (KiCad recomendado — gratuito e open source). Usar as atualizações desta revisão: LMR14020 (2A), AP2112K-3.3 (600mA), SI2359DS (−40V), SMCJ24A (SMD).
2. **PCB Layout — 4 camadas (recomendado):** Seguir stackup Signal/GND/PWR/Signal. Prioridade: plano GND intocado na camada 2; Buck no canto; GNSS no canto oposto com U.FL na borda.
3. **Verificação de Form Factor:** Confirmar que PCB ≤ 65×45mm, componentes ≤ 10mm de altura, antes de enviar para fabricação.
4. **DFM Check:** Verificar espaçamentos mínimos, via sizes, pasta de solda, thermal relief em componentes de potência.
5. **Protótipo V0.1:** Fabricar, testar todos os itens do checklist (Seções 7.1–7.7), com foco especial em:
   - Temperatura em caixa fechada a carga plena (Seção 7.6)
   - GNSS a 10Hz com antena externa (Seção 7.3)
   - Margem de corrente do Buck (medição real vs. power budget)
6. **Firmware Base (ESP-IDF):**
   - UART2 a 115200 baud para GNSS
   - Inicialização NEO-M9N para 10Hz via protocolo UBX (Seção 3.3.4)
   - TWAI (CAN nativo ESP32) a 500kbps
   - SPI para MicroSD com mutex para evitar contenção com expansão
   - ADC para V_BATT (GPIO 34) e temperatura NTC (GPIO 36)
   - Brownout detector configurado (threshold 2.43V)
7. **Integração com App:** Protocolo de comunicação (Bluetooth BLE — modo low-power para minimizar dissipação térmica) para o app Android V-Cortex futuro.

---

*Documento gerado em 2026-03-24 — V-Cortex Hardware Engineering Team*
*Revisão técnica v1.1 em 2026-03-24 — Análise de falhas críticas e melhorias para deploy em caixa OBD2*
