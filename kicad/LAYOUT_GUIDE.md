# V-Cortex PCB Layout Guide — KiCad 10 + JLCPCB

## 1. Configurações do Projeto KiCad

### 1.1 Board Setup (arquivo vcortex.kicad_pro já configurado)
- **Dimensões:** 65 × 45mm
- **Camadas:** 4 (Top Signal / GND Inner / PWR Inner / Bottom Signal)
- **Espessura:** 1.6mm
- **Acabamento:** ENIG (recomendado para U.FL e pads QFN)
- **Impedância controlada:** Sim (solicitar stackup para 50Ω microstrip no JLCPCB)

### 1.2 Netclasses já configuradas
| Netclass | Clearance | Track Width | Uso |
|----------|-----------|-------------|-----|
| Default | 0.15mm | 0.2mm | Sinais digitais |
| PWR | 0.3mm | 0.5mm | VBATT, +5V, +3V3 |
| CAN | 0.2mm | 0.25mm | CANH/CANL diferencial |
| RF | 0.15mm | **0.34mm** | Trilha U.FL 50Ω |

---

## 2. Stackup 4 Camadas (JLCPCB JLC04161H-7628)

```
Camada 1 (Top):    F.Cu — Sinais + componentes SMD top
Prepreg:           PP 7628 (0.21mm)
Camada 2 (GND):    In1.Cu — Plano GND CONTÍNUO (sem interrupções exceto keep-outs)
Core:              FR4 1.065mm
Camada 3 (PWR):    In2.Cu — Planos de potência (+5V, +3V3 copper fills)
Prepreg:           PP 7628 (0.21mm)
Camada 4 (Bottom): B.Cu — Sinais secundários + componentes bottom (mínimo)
```

**Impedância microstrip 50Ω no JLCPCB JLC04161H-7628:**
- Track width: 0.34mm na camada Top referenciada ao GND (camada 2)
- Calcular via: kicad.org/pcb-calculators ou saturn.pcb.com
- Ou solicitar ao JLCPCB: selecionar "Impedance control" e especificar 50Ω

---

## 3. Placement — Posicionamento dos Componentes

### 3.1 Diagrama de placement (vista Top)

```
         65mm
┌────────────────────────────────────────────────────────────┐
│  [OBD2 J1 - borda inferior, borda do PCB]                  │ ←←← encaixa na caixa
│                                                            │
│  [TVS1][F1][Q1]    [ESP32-WROOM-32E              ]         │
│  [Buck ][LDO]      [                              ]        │
│  zona PWR          [ antena PCB → borda DIREITA   ]  [GPS ]│
│  (copper fill      [                              ]  [NEO ]│
│   GND >=4cm2)      [         ]                    ] [U.FL]│
│                    [         ]                             │
│  [TCAN1044V][L9637D]   [CP2102N]   [MicroSD       ]       │
│  [CMC][PESD2CAN   ]   [USB conn]                          │
│  ←trilhas curtas→                                          │
└────────────────────────────────────────────────────────────┘
                                                        45mm
↑ Conector OBD2 posicionado na borda INFERIOR
  (macho sai para fora do PCB, encaixa na caixa OBD2)
```

### 3.2 Regras de placement por bloco

**Buck LMR14020 (canto superior esquerdo):**
- C_IN e C_BOOT: ≤2mm do IC
- C_BOUT1,2: ≤3mm do lado SW/output
- Loop de comutação mínimo: VIN_cap → SW_node → L_SW → VOUT_cap → GND_cap → IC
- Pad exposto GND: 9 thermal vias 0.3mm/0.6mm, copper fill GND ≥4cm²

**LDO AP2112K (adjacente ao Buck):**
- C_LDO_IN: ≤2mm do VIN
- C_LDO_OUT: ≤2mm do VOUT
- Copper fill GND sob o IC + 9 thermal vias
- Via de GND stitching ao redor

**ESP32-WROOM-32E (centro):**
- Antena PCB: aponta para borda direita do PCB
- Keep-out zone 15mm × 3mm: sem copper, vias, componentes abaixo da antena
- Todos os decoupling caps (C_MCU1,2,3): ≤3mm dos pinos de alimentação do módulo
- R_GPIO12 (pull-down): próximo ao pino GPIO12 do ESP32

**TCAN1044V + proteção CAN (próximo ao conector OBD2):**
- Ordem da borda para dentro: PESD2CAN → CMC1 → FB1/FB2 → TCAN1044V
- Trilhas CANH e CANL: paralelas, impedância diferencial ~120Ω, espaçamento ≤0.5mm entre elas
- Sem cruzamento com trilhas de sinal de alta frequência

**L9637D + proteção K-Line (adjacente ao TCAN):**
- TVS3 imediatamente após o conector OBD2 (pino 7)
- Jumper selecionável V_BAT (resistor 0R ou jumper de 2 pinos)

**NEO-M9N (canto superior direito, mais afastado do Buck):**
- Plano GND sólido sob o módulo (sem ilhas, sem splits)
- Trilha U.FL: 0.34mm, ≤20mm de comprimento, direto ao conector U.FL
- Sem outros componentes na mesma área (isolamento RF)
- Via stitching GND a cada 2mm ao redor da área GNSS

**CP2102N + USB (borda inferior, lado do conector USB):**
- Conector USB Micro-B ou USB-C na borda do PCB
- Ferrite em série com VBUS (+5V do USB)
- Q2/Q3 BC817 próximos ao CP2102N e aos pinos EN/GPIO0 do ESP32

**MicroSD (abaixo do ESP32):**
- Slot horizontal push-push, borda acessível

---

## 4. Roteamento — Regras Críticas

### 4.1 Power (Camada Top + Camada PWR)
```
VBATT_PROT: 1.0mm (até 2A máx da placa)
+5V:        0.5mm (até 2A máx do Buck)
+3V3:       0.5mm (até 600mA máx do LDO)
GND ret:    via copper fill em todas as camadas
```

### 4.2 Buck — Loop de Comutação (Camada Top)
```
CRÍTICO: área do loop = L_SW × I_SW × dI/dt → EMI
Menor área = menos EMI = melhor regulação

VIN_cap (C_IN) ──→ pino VIN LMR14020
              └──→ pino SW (via indutor L_SW)
                         └──→ VOUT_cap (C_BOUT)
                                    └──→ pino GND (retorno direto)

Rotear TUDO nesta ordem, sem desvios
```

### 4.3 CAN Diferencial (Camada Top ou Bottom)
- Par CANH/CANL: roteados juntos, mesma camada, espaçamento 0.2mm entre trilhas
- Comprimento de CANH = comprimento de CANL (mismatch < 5mm)
- Impedância diferencial ≈ 120Ω (verificar com calculadora)
- Terminação 120Ω o mais próximo possível do final do barramento

### 4.4 RF — Trilha U.FL 50Ω (Camada Top)
```
NEO-M9N RF_IN ─── [trilha 0.34mm] ─── U.FL J_ANT

Regras:
- Largura exata: 0.34mm (±0.01mm)
- Comprimento: mínimo possível (< 20mm ideal)
- Sem vias ao longo da trilha
- 45° nos cantos (não 90°)
- Clearance de 1.0mm para qualquer outro sinal
- Copper fill GND lateral de ambos os lados (coplanar waveguide - opcional mas melhor)
```

### 4.5 GND Stitching (Todas as camadas)
- Via de stitching GND 0.3mm/0.6mm a cada 5mm em toda a placa
- Via array ao redor de loops de alta frequência (Buck, CAN)
- Via array ao redor da área RF do GNSS (2mm entre vias)

---

## 5. Gerenciamento Térmico

### 5.1 Thermal Via Arrays

**LMR14020 (pad exposto 1.6×1.3mm):**
- 9× vias 0.3mm drill em grid 3×3
- Conectam pad exposto ao plano GND (camada 2)
- Copper fill no Top copper sob o IC (≥4cm²)

**AP2112K-3.3 (pad GND pino 2):**
- Pad GND alargado + 4-9 thermal vias
- Copper fill GND ≥4cm² na área do LDO

### 5.2 Copper Pours (zonas de copper)
| Rede | Camada | Área mínima | Prioridade |
|------|--------|-------------|------------|
| GND | All 4 layers | 100% disponível | Máxima |
| +5V | In2.Cu (PWR) | ≥10cm² | Alta |
| +3V3 | In2.Cu (PWR) | ≥5cm² | Alta |

---

## 6. Checklist DRC KiCad (antes de exportar)

### 6.1 ERC (Electrical Rules Check)
- [ ] Nenhum "pin não conectado" não intencional
- [ ] Nenhum "wire sem terminação"
- [ ] GPIO12 tem pull-down para GND (não pull-up!)
- [ ] GPIO0 tem pull-up para +3V3
- [ ] GPIO5 tem pull-up para +3V3

### 6.2 DRC (Design Rules Check)
- [ ] Clearance mínimo 0.15mm — sem violações
- [ ] Via drill mínimo 0.3mm — todas as vias OK
- [ ] Copper to edge clearance 0.3mm — sem violações
- [ ] Trilha RF U.FL = 0.34mm ±0.01mm
- [ ] Thermal vias presentes sob LMR14020 e AP2112K

### 6.3 Verificação Visual (3D View KiCad)
- [ ] Antena ESP32 não coberta por outros componentes ou copper
- [ ] Conector OBD2 alinhado com borda do PCB
- [ ] Conector U.FL acessível
- [ ] Slot MicroSD acessível
- [ ] Conector USB acessível
- [ ] Nenhum componente > 10mm de altura no Top

---

## 7. Exportação para JLCPCB

### 7.1 Gerber Files (File → Fabrication Outputs → Gerbers)
```
Layers a exportar:
✓ F.Cu (Top copper)
✓ In1.Cu (GND inner)
✓ In2.Cu (PWR inner)
✓ B.Cu (Bottom copper)
✓ F.Mask (Solder mask top)
✓ B.Mask (Solder mask bottom)
✓ F.Silkscreen
✓ B.Silkscreen (se houver componentes no bottom)
✓ F.Courtyard (verificação)
✓ Edge.Cuts (contorno da placa)

Configurações:
- Formato: RS-274X
- Casas decimais: 5
- Unidade: mm
- Incluir atributos do footprint: Sim
- Comprimir em ZIP
```

### 7.2 Drill Files
```
- Formato: Excellon
- Unidade: mm
- Zeros: trailing zeros suprimidos
- Mapa de drill: PDF (opcional)
- Arquivo: vcortex.drl
```

### 7.3 BOM para PCBA (via Plugin JLCPCB Tools)
```
Instalar: KiCad Plugin Manager → "JLCPCB Tools" by Bouni
Uso: Tools → JLCPCB Tools → Generate BOM
Arquivo: vcortex_bom_jlcpcb.csv (já preparado em /bom/)

Formato gerado:
Comment,Designator,Footprint,JLCPCB Part#
100nF,C_IN;C_BOOT;...,0402,C14663
...
```

### 7.4 CPL — Component Placement List (via Plugin)
```
Tools → JLCPCB Tools → Generate CPL
ATENÇÃO: JLCPCB usa convenção de ângulo diferente do KiCad
O plugin JLCPCB Tools converte automaticamente os ângulos
Verificar: cada componente com ângulo correto no preview do JLCPCB
```

---

## 8. Configuração no Site JLCPCB

### 8.1 PCB Order
```
PCB Layers: 4
PCB Dimensions: 65 x 45mm
PCB Thickness: 1.6mm
Surface Finish: ENIG (recomendado) ou HASL Lead-Free
Min Track/Spacing: 6/6mil (0.15mm) — compatível com nosso design
Min Hole Size: 0.3mm — compatível
Via Covering: Tented Vias
Impedance Control: YES — 50Ω Single-Ended (trilha U.FL)
  → Selecionar stackup JLC04161H-7628
  → Confirmar: camada 1, largura 0.34mm = 50Ω
PCB Color: Green (mais barato) ou Black
Silkscreen: White
```

### 8.2 PCB Assembly
```
PCBA Type: Economic (se todos SMD num lado) ou Standard
Assembly Side: Top Side
Tooling Holes: Added by JLCPCB (automatic)
Confirm Parts Placement: YES (revisar cada parte antes de confirmar)
```

### 8.3 BOM Upload
```
Upload: bom/vcortex_bom_jlcpcb.csv
Mapear colunas:
  Component: Value
  Designator: Reference
  Footprint: Footprint_KiCad
  JLCPCB Part#: LCSC_Part
```

### 8.4 NEO-M9N-00B (Global Sourcing)
```
Para este componente específico:
Opção A: JLCPCB Global Sourcing Parts
  → Na tela de BOM, clicar "Search" para NEO-M9N-00B
  → Se disponível via Global Sourcing, adicionar
  → Custo adicional cobrado

Opção B: Consignment (usuário envia os chips)
  → Comprar NEO-M9N-00B (Mouser #672-NEO-M9N-00B ou DigiKey)
  → Enviar para fábrica JLCPCB com número do pedido
  → JLCPCB monta os chips fornecidos
  → Verificar instruções de consignment no site JLCPCB
```

### 8.5 OBD2 Connector (Não Montado)
```
O conector OBD2 J1 NÃO está na lista de PCBA
→ Deixar fora do BOM de PCBA
→ Marcar como DNP (Do Not Place) no CPL se necessário
→ Soldar manualmente após receber a placa:
   1. Inserir conector pelos furos do PCB
   2. Soldar com ferro de solda (THT simples, pinos grandes)
   3. Verificar continuidade: pino 16 → VBATT, pino 4/5 → GND, pino 6 → CANH, etc.
```

---

## 9. Pedido Mínimo e Custo Estimado

| Item | Qtd | Custo Estimado |
|------|-----|----------------|
| PCB 4L ENIG 65×45mm | 5 | ~$20-30 |
| PCBA Economic | 5 | ~$30-50 (setup) + componentes |
| Basic Parts (resistores/caps) | múltiplos | ~$1-5 total |
| Extended Parts (~10 tipos) | múltiplos | ~$30 (setup $3/tipo) |
| NEO-M9N-00B (Global Sourcing) | 5 | ~$25-35 por unidade |
| **Total estimado** | **5 placas** | **~$200-300 USD** |

*Valores aproximados, verificar cotação atual no site JLCPCB*
