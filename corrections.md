# V-Cortex Hardware — Correções Pendentes (rev v1.2 → v1.3)

Review realizado por análise comparativa entre esquemáticos KiCad (rev v1.2),
BOM JLCPCB e decisões de design documentadas no projeto.

Severidades: **CRÍTICO** (falha garantida) | **ALTO** (funcionalidade/fabricação) | **MÉDIO** (robustez/supply chain)

---

## Etapa 1 — Power: pwr.kicad_sch + bom_jlcpcb.csv

### [CRÍTICO] Q1 — MOSFET: VDS do JSMSEMI não verificado

| Campo | Valor |
|-------|-------|
| Componente | Q1 (proteção reversão de polaridade) |
| Arquivo | `bom/vcortex_bom_jlcpcb.csv` linha 2 |
| Problema | LCSC C53113978 é JSMSEMI PMV45EN2R-JSM. O BOM afirma |VDS|=40V, mas o Nexperia PMV45EN2R original tem |VDS|=**30V**. JSMSEMI é fabricante chinês — o mesmo número de peça não garante mesmas specs. |
| Risco | TVS SMDJ22A clamps a **35.5V** durante load dump. Se |VDS| real = 30V, o MOSFET é destruído. Regra do projeto: |VDS| ≥ 40V obrigatório. |
| BOM original | SI2359DS Vishay — |VDS|=40V verificado, mas sem código LCSC |

**Ação obrigatória antes de ordernar:**
1. Acessar LCSC e baixar o datasheet do C53113978 (JSMSEMI PMV45EN2R-JSM)
2. Confirmar VDS(max) no datasheet
3. Se VDS = 30V → substituir por **C426872** (Nexperia PMV45EN2R, |VDS|=30V... também 30V!)
   ou buscar P-MOSFET SMD SOT-23 com |VDS| ≥ 40V, ID ≥ 3A disponível no LCSC
   Candidatos: AO3401A (|VDS|=30V — insuficiente), DMP3098L-7 (|VDS|=30V — insuficiente),
   **IRF9Z14S** equiv SMD 40V, ou buscar "P-channel MOSFET -40V SOT-23" no LCSC

---

### [ALTO] F1 — Polyfuse: rated 30V, exposta a 35.5V (load dump)

| Campo | Valor |
|-------|-------|
| Componente | F1 (Littelfuse 1812L300MR, LCSC C127824) |
| Arquivo | `kicad/sheets/pwr.kicad_sch` — Bloco 1 |
| Problema | Topologia: VBATT → Q1 → **F1** → nó → TVS1. F1 fica **upstream** da TVS. Durante load dump ISO7637-2 pulso 5 (+87V/400ms), a tensão sobe até TVS clamp (35.5V) antes da TVS ativar. F1 vê 35.5V. Rating máximo: **30V**. |
| Risco | F1 pode falhar por overvoltage em condições de load dump, travando em modo aberto (circuito aberto permanente) |

**Ação:**
- Substituir F1 por polyfuse rated **60V**:
  - Opção 1: **Littelfuse 1812L300/60WR** — mesmo footprint 1812, 3A hold, 60V
  - Opção 2: **Bourns MF-MSMF300/60-2** — 1812, 3A hold, 60V
  - Verificar disponibilidade LCSC de ambas antes de decidir
- Atualizar LCSC e MPN em `bom/vcortex_bom_jlcpcb.csv` linha 4

---

## Etapa 2 — BOM: Sincronização de Arquivos

### [ALTO] vcortex_bom_resolved.csv — Arquivo obsoleto com nome enganoso

| Campo | Valor |
|-------|-------|
| Arquivo | `bom/vcortex_bom_resolved.csv` |
| Problema | O nome "resolved" sugere arquivo final/resolvido, mas contém os valores **pré-correção** da BOM. Um engenheiro que usar este arquivo para produção vai fabricar placas com defeito. |

**Discrepâncias críticas encontradas (resolved vs jlcpcb):**

| Referência | resolved.csv (ERRADO) | jlcpcb.csv (CORRETO) |
|------------|----------------------|----------------------|
| R_BOT_BK | 56.2k 1% | **18k 1%** (LCSC C25762) |
| F1 | MF-MSMF300 Bourns (sem LCSC) | **1812L300MR C127824** |
| C_BOUT1/C_BOUT2 | footprint 1206 | **footprint 0805** (LCSC C380338) |
| Q1 | SI2359DS (sem LCSC) | **PMV45EN2R-JSM C53113978** |
| Q3 | LCSC C916383 | **C22400355** (mesmo que Q2) |
| L_FILT | Ausente (listado em Stage 5 GNSS) | **Presente em Stage 1 Power** |

**Ação:**
1. Adicionar na linha 1 do arquivo: `# OBSOLETO — Ver vcortex_bom_jlcpcb.csv para produção`
2. Renomear: `vcortex_bom_resolved.csv` → `vcortex_bom_v1_draft.csv`

---

## Etapa 3 — CAN / K-Line: can_kline.kicad_sch

### [ALTO] K-Line RX — GPIO33 exposto a 5V sem proteção

| Campo | Valor |
|-------|-------|
| Componente | U_LS1 (74LVC1T45GW, LCSC C478004), GPIO33 (KLINE_RX) |
| Arquivo | `kicad/sheets/can_kline.kicad_sch` — Bloco K-Line |
| Problema | O schematic descreve "L9637D pino1 (RXD) → 74LVC1T45 pino B → GPIO33". Mas o U_LS1 é descrito na BOM como "Level shifter 3.3V→5V KLINE TX" (direção fixa A→B). Se a direção é fixa TX, então L9637D RXD (saída **5V**) chega direto ao GPIO33 sem conversão. ESP32 GPIO33 suporta max **3.3V** → **dano ao ESP32 garantido**. |

**Ação — escolher uma opção:**

**Opção A (recomendada — simples):** Adicionar divisor resistivo no RXD do L9637D
```
L9637D RXD (pino 1) ──[R_KRXA 10k]──┬── GPIO33
                                      │
                                   [R_KRXB 20k]
                                      │
                                     GND
```
- V_GPIO33 = 5V × 20k/30k = **3.33V** ✓ (mesmo conceito do CAN_RX)
- Adicionar R_KRXA (10k, C60490) e R_KRXB (20k, C93942) ao schematic e BOM
- Remover conexão direta RXD → GPIO33 do texto do schematic

**Opção B:** Usar DIR do 74LVC1T45 controlado por firmware
- Adicionar fio DIR do U_LS1 a um GPIO livre (ex: GPIO27 atualmente em expansão)
- TX: DIR=HIGH (A→B, GPIO15 → L9637D TXD)
- RX: DIR=LOW (B→A, L9637D RXD → GPIO33)
- Mais complexo: firmware deve comutar DIR antes de cada operação half-duplex

---

## Etapa 4 — GNSS: periph.kicad_sch + bom_jlcpcb.csv

### [CRÍTICO] C_GNSS_10N — Código LCSC errado (X7R entregue em vez de NP0)

| Campo | Valor |
|-------|-------|
| Componente | C_GNSS_10N (bypass VCC_IO NEO-M9N, deve ser 10nF NP0/C0G) |
| Arquivo | `bom/vcortex_bom_jlcpcb.csv` linha 69 |
| Problema | LCSC atribuído: **C15849** = Yageo CC0402KRX7R9BB103 = **10nF X7R**. O mesmo código de C_BOUT4. NEO-M9N application note exige NP0/C0G no pino VCC_IO (capacitância X7R varia com frequência e temperatura, degradando o RF front-end em 1575MHz). |
| Risco | JLCPCB monta X7R nos dois footprints (C_BOUT4 e C_GNSS_10N). GNSS pode ter performance reduzida ou instabilidade. |

**Ação:**
1. Buscar no LCSC: "10nF NP0 C0G 0402" — ex: Yageo CC0402JRNPO9BN103
2. Confirmar código LCSC correto (NP0, não X7R)
3. Atualizar linha 69 do `bom/vcortex_bom_jlcpcb.csv`:
   - LCSC: `C15849` → código NP0 correto
   - MPN: manter `CC0402JRNPO9BN103`
   - Também atualizar o schematic `kicad/sheets/periph.kicad_sch` se tiver o código listado

---

### [MÉDIO] BAT1 — Footprint 12.8×6mm: verificar espaço no layout

| Campo | Valor |
|-------|-------|
| Componente | BAT1 (supercap backup GNSS, Yezhan C6075487) |
| Arquivo | `kicad/vcortex.kicad_pcb` (a verificar) |
| Problema | Footprint mudou de 3.2×2.5mm (CPX3225A original) para 12.8×6.0mm (Yezhan ASR-M-10-0.1F). Área 9.6× maior em um PCB 65×45mm com layout denso. |

**Ação:**
1. Abrir `kicad/vcortex.kicad_pcb` e verificar se o footprint de BAT1 foi atualizado
2. Confirmar que há espaço disponível na região GNSS (canto quieto, longe do Buck)
3. Se o PCB layout não foi criado ainda: reservar área 14×8mm para BAT1 + clearance

---

## Etapa 5 — Supply Chain / Estoque

### [MÉDIO] NEO-M9N-00B — Global Sourcing: prazo e custo incertos

| Componente | LCSC | Status |
|------------|------|--------|
| U_GNSS (NEO-M9N-00B) | GLOBAL_SOURCING | Não disponível via PCBA padrão JLCPCB |

**Ação antes de ordernar:**
- Entrar em contato com JLCPCB para cotação Global Sourcing do NEO-M9N-00B
- Alternativa: comprar separado no Mouser/DigiKey e enviar consignment para JLCPCB
- Alternativa de backup: NEO-M8N-0-10 (geração anterior, mais disponível, 10Hz via UBX)

---

### [MÉDIO] L9637D — Estoque baixo (C153038: ~1035 unidades)

| Componente | LCSC | Estoque | Risco |
|------------|------|---------|-------|
| U_KLINE (L9637D) | C153038 | ~1035 unid | Parte legada, estoque pode zerar |

**Ação:**
- Verificar estoque atual na LCSC antes de ordernar
- Alternativa: **MC33290** (NXP) — mesmo protocolo ISO9141/KWP2000, verificar pinagem
  e se SOIC-8 é compatível antes de trocar

---

### [MÉDIO] FB1/FB2/FB_GNSS/FB_USB — Verificar estoque (C41556732)

| Componente | LCSC | Estoque | Necessário (5 placas) |
|------------|------|---------|----------------------|
| BLM21PG601SN1D (×4 por placa) | C41556732 | ~480 unid | 20 unid mínimo |

Estoque suficiente para lote inicial. Monitorar se escalar.

---

## Resumo Executivo

| # | Severidade | Item | Status |
|---|-----------|------|--------|
| 1 | CRÍTICO ✅ | C_GNSS_10N LCSC errado (X7R vs NP0) | **RESOLVIDO** — C3855387 muRata GRM1555C1E103JE01D (C0G 25V) |
| 2 | CRÍTICO ✅ | Q1 VDS do JSMSEMI não confirmado | **RESOLVIDO** — datasheet C53113978 confirma VDS(max)=-40V; alertas adicionados à BOM |
| 3 | ALTO ✅ | K-Line RX: GPIO33 exposto a 5V | **RESOLVIDO** — R_KRXA (10k C60490) + R_KRXB (20k C93942) adicionados ao schematic e BOM |
| 4 | ALTO ✅ | F1 rated 30V, TVS clamps 35.5V | **RESOLVIDO** — substituído por MF-MSMF300/60-2 Bourns (60V, C383507) |
| 5 | ALTO ✅ | bom_resolved.csv obsoleto e enganoso | **RESOLVIDO** — renomeado para vcortex_bom_v1_draft.csv + header OBSOLETO |
| 6 | MÉDIO ⚠️ | BAT1 footprint 12.8×6mm vs layout PCB | **PENDENTE** — verificar kicad/vcortex.kicad_pcb quando layout for criado |
| 7 | MÉDIO ⚠️ | NEO-M9N Global Sourcing | **PENDENTE** — cotar JLCPCB antes de ordernar; notas adicionadas à BOM/schematic |
| 8 | MÉDIO ⚠️ | L9637D estoque baixo (~1035 unid) | **PENDENTE** — verificar estoque antes de ordernar; alerta adicionado à BOM |
| 9 | MÉDIO ✅ | LMR14020 VOUT pode chegar a 5.24V | **DOCUMENTADO** — aceitável (5V±10% para todos os componentes) |

**Itens verificados e corretos (não alterar):**
GPIO12 pull-down ✓ | Buck 18k (5V) ✓ | R_S 10Ohm ✓ | C_DTR/C_RTS ✓ |
CAN divider 10k/20k ✓ | CAN TX direto ✓ | C_K_VCC 10uF ✓ | L_FILT 10uH ✓ |
Auto-prog BC817 ✓ | Bias-T GNSS ✓ | Supercap GNSS ✓ | Terminação CAN GPIO25 ✓
