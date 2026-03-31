#!/usr/bin/env python3
"""
V-Cortex LCSC Stock Checker
Valida disponibilidade de componentes da BOM na LCSC.

Uso:
  python lcsc_stock_checker.py --bom ../bom/vcortex_bom.csv
  python lcsc_stock_checker.py --bom ../bom/vcortex_bom.csv --stage 1
  python lcsc_stock_checker.py --part C123456
  python lcsc_stock_checker.py --bom ../bom/vcortex_bom.csv --output ../bom/stock_report.csv
"""

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Windows: garante saída UTF-8 no console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Dependencias nao instaladas. Execute:")
    print("  pip install -r requirements.txt")
    sys.exit(1)


# --- Constantes ---

LCSC_PAGE_URL = "https://www.lcsc.com/product-detail/{part}.html"
LCSC_API_URL = "https://wmsc.lcsc.com/wmsc/product/detail"
LOW_STOCK_THRESHOLD = 100
MAX_RETRIES = 3
DEFAULT_DELAY = 2.0

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.lcsc.com/",
    "Connection": "keep-alive",
}

STATUS_LABELS = {
    "in_stock":    "[OK] ",
    "low_stock":   "[LOW]",
    "out_of_stock":"[OUT]",
    "not_found":   "[404]",
    "not_on_lcsc": "[N/A]",
    "error":       "[ERR]",
}

STAGE_NAMES = {
    1: "Stage 1 — Power Supply",
    2: "Stage 2 — MCU Core + USB",
    3: "Stage 3 — CAN Bus",
    4: "Stage 4 — K-Line",
    5: "Stage 5 — GNSS",
    6: "Stage 6 — Storage & Expansão",
}


# --- Data classes ---

@dataclass
class ProductInfo:
    lcsc_part: str
    manufacturer: str = ""
    mpn: str = ""
    description: str = ""
    package: str = ""
    stock: int = 0
    unit_price: float = 0.0
    status: str = "error"
    url: str = ""
    raw_error: str = ""


@dataclass
class BOMRow:
    reference: str
    value: str
    mpn: str
    footprint: str
    lcsc_part: str
    manufacturer: str
    description: str
    stage: int
    qty: int
    notes: str
    product: ProductInfo = field(default=None)


# --- LCSC Client ---

class LCSCClient:
    def __init__(self, rate_limit: float = DEFAULT_DELAY):
        self.session = requests.Session()
        self.session.headers.update(BROWSER_HEADERS)
        self.rate_limit = rate_limit
        self._last_request_time = 0.0

    def _throttle(self):
        elapsed = time.time() - self._last_request_time
        wait = self.rate_limit - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_time = time.time()

    def _classify_stock(self, qty: int) -> str:
        if qty >= LOW_STOCK_THRESHOLD:
            return "in_stock"
        elif qty > 0:
            return "low_stock"
        return "out_of_stock"

    def _parse_html(self, html: str, lcsc_part: str) -> ProductInfo:
        """Extrai dados do produto da página HTML da LCSC.

        LCSC usa Nuxt SSR. O JSON-LD <script type="application/ld+json"> com
        @type=Product contém: name, sku (LCSC code), mpn, brand, price,
        inventoryLevel e availability. É a fonte mais confiável.
        """
        soup = BeautifulSoup(html, "html.parser")
        info = ProductInfo(
            lcsc_part=lcsc_part,
            url=LCSC_PAGE_URL.format(part=lcsc_part),
        )

        # JSON-LD com @type=Product — fonte principal de dados
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if not (isinstance(data, dict) and data.get("@type") == "Product"):
                    continue

                info.description = data.get("name", "")
                info.mpn = data.get("mpn", "") or data.get("sku", "")
                info.manufacturer = data.get("brand", "")

                offers = data.get("offers", {})
                try:
                    info.unit_price = float(offers.get("price", 0) or 0)
                except (TypeError, ValueError):
                    pass

                # inventoryLevel é o campo mais direto para stock
                try:
                    info.stock = int(offers.get("inventoryLevel", 0) or 0)
                except (TypeError, ValueError):
                    pass

                # Se inventoryLevel não vier, usa availability como fallback
                if info.stock == 0:
                    avail = offers.get("availability", "")
                    if "InStock" in avail:
                        stock_from_html = self._extract_stock_span(soup)
                        info.stock = stock_from_html if stock_from_html else 1

                break
            except (json.JSONDecodeError, AttributeError):
                continue

        # Fallback: procura stock no span renderizado se JSON-LD não trouxe
        if info.stock == 0 and info.description:
            stock_from_html = self._extract_stock_span(soup)
            if stock_from_html:
                info.stock = stock_from_html

        # Extrai encapsulamento da tabela de specs (não está no JSON-LD)
        self._extract_package(soup, info)

        if not info.description.strip() and info.stock == 0:
            info.status = "not_found"
        else:
            info.description = info.description.strip()
            info.status = self._classify_stock(info.stock)

        return info

    def _extract_stock_span(self, soup: BeautifulSoup):
        """Extrai stock do span 'In-Stock: X,XXX' renderizado pelo SSR."""
        import re as _re
        # Estratégia 1: span com texto "In-Stock: N" (classe fz-20 ou font-Bold)
        for tag in soup.find_all("span"):
            txt = tag.get_text(" ", strip=True)
            if "In-Stock" in txt or "In Stock" in txt:
                m = _re.search(r"([\d,]+)", txt)
                if m:
                    return int(m.group(1).replace(",", ""))

        # Estratégia 2: procura padrão no inventoryLevel dentro do JSON-LD alternativo
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                offers = data.get("offers", {})
                lvl = offers.get("inventoryLevel")
                if lvl is not None:
                    return int(lvl)
            except Exception:
                continue

        return None

    def _extract_package(self, soup: BeautifulSoup, info: ProductInfo):
        """Extrai encapsulamento (package) da tabela de specs do produto."""
        import re as _re
        for row in soup.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                value = cells[1].get_text(strip=True)
                if "package" in label or "case" in label or "encap" in label:
                    info.package = value
                    break

    def _query_api(self, lcsc_part: str) -> ProductInfo:
        """Tenta a API interna da LCSC como fallback."""
        info = ProductInfo(
            lcsc_part=lcsc_part,
            url=LCSC_PAGE_URL.format(part=lcsc_part),
        )
        try:
            resp = self.session.get(
                LCSC_API_URL,
                params={"productCode": lcsc_part},
                timeout=10,
            )
            if resp.status_code != 200:
                info.status = "not_found" if resp.status_code == 404 else "error"
                info.raw_error = f"HTTP {resp.status_code}"
                return info

            data = resp.json()
            product = data.get("result") or {}
            if not product:
                info.status = "not_found"
                return info

            info.description = product.get("productIntroEn", product.get("productModel", ""))
            info.mpn = product.get("productModel", "")
            info.manufacturer = product.get("brandNameEn", product.get("brandName", ""))
            info.package = product.get("encapStandard", "")

            stock = product.get("stockNumber", product.get("stock", 0))
            try:
                info.stock = int(stock)
            except (TypeError, ValueError):
                info.stock = 0

            prices = product.get("productPriceList", [])
            if prices:
                try:
                    info.unit_price = float(prices[0].get("usdPrice", prices[0].get("price", 0)))
                except (TypeError, ValueError, IndexError):
                    pass

            info.status = self._classify_stock(info.stock)

        except requests.exceptions.RequestException as e:
            info.status = "error"
            info.raw_error = str(e)
        except (json.JSONDecodeError, KeyError) as e:
            info.status = "error"
            info.raw_error = f"Parse error: {e}"

        return info

    def search_by_mpn(self, mpn: str, top_n: int = 5) -> list[ProductInfo]:
        """Busca por MPN usando a API EasyEDA Pro (espelha catálogo LCSC).

        Retorna lista de ProductInfo ordenada por stock decrescente.
        Usa a API pública do EasyEDA Pro que indexa o catálogo LCSC completo.
        """
        EASYEDA_URL = "https://pro.easyeda.com/api/eda/product/search"
        self._throttle()

        try:
            resp = self.session.get(
                EASYEDA_URL,
                params={
                    "keyword": mpn,
                    "currentPage": 1,
                    "pageSize": top_n,
                    "type": "LCSC",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            if data.get("code") != 0:
                return []

            products = data.get("result", {}).get("productList", [])
            results = []
            for p in products:
                lcsc_code = p.get("number", "")
                stock = p.get("stock", p.get("stockNumber", 0))
                try:
                    stock = int(stock)
                except (TypeError, ValueError):
                    stock = 0

                price_list = p.get("price", [])
                unit_price = 0.0
                if price_list:
                    try:
                        unit_price = float(price_list[0][1]) if len(price_list[0]) > 1 else 0.0
                    except (TypeError, ValueError, IndexError):
                        pass

                info = ProductInfo(
                    lcsc_part=lcsc_code,
                    manufacturer=p.get("manufacturer", ""),
                    mpn=p.get("mpn", ""),
                    description=p.get("mpn", ""),
                    package=p.get("package", ""),
                    stock=stock,
                    unit_price=unit_price,
                    status=self._classify_stock(stock),
                    url=f"https://www.lcsc.com{p.get('url', '')}",
                )
                results.append(info)

            # Ordena: em estoque primeiro, depois por stock decrescente
            results.sort(key=lambda x: (x.status == "not_found", -x.stock))
            return results

        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError):
            return []

    def get_product(self, lcsc_part: str) -> ProductInfo:
        """Consulta LCSC para um part number. Tenta HTML primeiro, API como fallback."""
        if not re.match(r"^C\d+$", lcsc_part, re.I):
            return ProductInfo(
                lcsc_part=lcsc_part,
                status="error",
                raw_error="Formato inválido (esperado: C######)",
                url="",
            )

        url = LCSC_PAGE_URL.format(part=lcsc_part)
        info = ProductInfo(lcsc_part=lcsc_part, url=url)

        for attempt in range(1, MAX_RETRIES + 1):
            self._throttle()
            try:
                resp = self.session.get(url, timeout=10)

                if resp.status_code == 429:
                    wait = min(5 * (2 ** (attempt - 1)), 60)
                    print(f"    Rate limited. Aguardando {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                    continue

                if resp.status_code == 404:
                    info.status = "not_found"
                    return info

                if resp.status_code != 200:
                    info.status = "error"
                    info.raw_error = f"HTTP {resp.status_code}"
                    if attempt == MAX_RETRIES:
                        return info
                    continue

                # HTML obtido com sucesso
                parsed = self._parse_html(resp.text, lcsc_part)

                # Se HTML não deu resultado útil, tenta API como fallback
                if parsed.status == "not_found" and attempt == 1:
                    api_result = self._query_api(lcsc_part)
                    if api_result.status not in ("not_found", "error"):
                        return api_result

                return parsed

            except requests.exceptions.Timeout:
                info.raw_error = "Timeout"
                if attempt == MAX_RETRIES:
                    info.status = "error"
                    return info
                time.sleep(2)

            except requests.exceptions.ConnectionError as e:
                info.status = "error"
                info.raw_error = f"Connection error: {e}"
                return info

        info.status = "error"
        return info


# --- BOM Validator ---

class BOMValidator:
    def __init__(self, bom_path: str):
        self.bom_path = Path(bom_path)
        self.rows: list[BOMRow] = self._load_csv()

    def _load_csv(self) -> list[BOMRow]:
        rows = []
        with open(self.bom_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for line in reader:
                try:
                    stage = int(line.get("Stage", 0) or 0)
                    qty = int(line.get("Qty", 1) or 1)
                except ValueError:
                    stage, qty = 0, 1

                rows.append(BOMRow(
                    reference=line.get("Reference", ""),
                    value=line.get("Value", ""),
                    mpn=line.get("MPN", ""),
                    footprint=line.get("Footprint", ""),
                    lcsc_part=(line.get("LCSC_Part") or "").strip(),
                    manufacturer=line.get("Manufacturer", ""),
                    description=line.get("Description", ""),
                    stage=stage,
                    qty=qty,
                    notes=line.get("Notes", ""),
                ))
        return rows

    def validate(self, client: LCSCClient, stage_filter: int = None) -> list[BOMRow]:
        rows = self.rows
        if stage_filter is not None:
            rows = [r for r in rows if r.stage == stage_filter]

        total = len(rows)
        print(f"\nVerificando {total} componentes na LCSC...")
        if stage_filter:
            print(f"(Filtro: {STAGE_NAMES.get(stage_filter, f'Stage {stage_filter}')})\n")

        for i, row in enumerate(rows, 1):
            prefix = f"  [{i:2d}/{total}] {row.reference:<12} {row.value:<25}"

            if not row.lcsc_part:
                row.product = ProductInfo(
                    lcsc_part="",
                    status="not_on_lcsc",
                    url="",
                )
                print(f"{prefix} -> NAO ESTA NA LCSC")
                continue

            print(f"{prefix} -> {row.lcsc_part}...", end="", flush=True)
            row.product = client.get_product(row.lcsc_part)

            status = row.product.status
            stock = row.product.stock
            price = row.product.unit_price

            if status == "in_stock":
                print(f" Stock: {stock:>7,}  ${price:.4f}")
            elif status == "low_stock":
                print(f" Stock: {stock:>7,}  ${price:.4f}  << ESTOQUE BAIXO")
            elif status == "out_of_stock":
                print(f" SEM ESTOQUE  << PRECISA ALTERNATIVA")
            elif status == "not_found":
                print(f" NAO ENCONTRADO na LCSC")
            else:
                print(f" ERRO: {row.product.raw_error}")

        return rows

    def print_summary(self, rows: list[BOMRow]):
        counts = {s: 0 for s in STATUS_LABELS}
        by_stage: dict[int, list[BOMRow]] = {}

        for row in rows:
            if row.product:
                counts[row.product.status] = counts.get(row.product.status, 0) + 1
                by_stage.setdefault(row.stage, []).append(row)

        print("\n" + "=" * 70)
        print("RELATORIO DE ESTOQUE — V-Cortex BOM")
        print("=" * 70)

        for stage_num in sorted(by_stage.keys()):
            stage_rows = by_stage[stage_num]
            name = STAGE_NAMES.get(stage_num, f"Stage {stage_num}")
            print(f"\n{name}:")
            for row in stage_rows:
                if not row.product:
                    continue
                label = STATUS_LABELS.get(row.product.status, "[???]")
                lcsc = row.lcsc_part or "—"
                stock_str = f"Stock: {row.product.stock:>7,}" if row.product.stock else "              "
                price_str = f"${row.product.unit_price:.4f}" if row.product.unit_price else "       "
                print(f"  {label} {row.reference:<12} {row.value:<25} {lcsc:<12} {stock_str}  {price_str}")
                if row.product.status in ("out_of_stock", "not_found"):
                    if row.notes:
                        print(f"         NOTA: {row.notes}")
                if row.product.status == "not_on_lcsc" and row.notes:
                    print(f"         FONTE: {row.notes}")

        print("\n" + "-" * 70)
        total = sum(counts.values())
        print(f"Total verificado:  {total}")
        print(f"  Em estoque:      {counts.get('in_stock', 0)}")
        print(f"  Estoque baixo:   {counts.get('low_stock', 0)}")
        print(f"  Sem estoque:     {counts.get('out_of_stock', 0)}")
        print(f"  Nao encontrado:  {counts.get('not_found', 0)}")
        print(f"  Nao na LCSC:     {counts.get('not_on_lcsc', 0)}")
        print(f"  Erro de consulta:{counts.get('error', 0)}")
        print("=" * 70)

        problems = [
            r for r in rows
            if r.product and r.product.status in ("out_of_stock", "not_found", "error")
        ]
        if problems:
            print(f"\nACOES NECESSARIAS ({len(problems)} componentes):")
            for row in problems:
                url = LCSC_PAGE_URL.format(part=row.lcsc_part) if row.lcsc_part else ""
                print(f"  - {row.reference} ({row.mpn}): {row.product.status.upper()}")
                if row.notes:
                    print(f"    Alternativa sugerida: {row.notes}")
                if url:
                    print(f"    URL: {url}")

    def save_report(self, rows: list[BOMRow], output_path: str):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "Reference", "Value", "MPN", "Footprint", "LCSC_Part",
            "Manufacturer", "Description", "Stage", "Qty",
            "Stock", "Price_USD", "Status", "URL", "Notes",
        ]

        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                p = row.product
                writer.writerow({
                    "Reference": row.reference,
                    "Value": row.value,
                    "MPN": row.mpn,
                    "Footprint": row.footprint,
                    "LCSC_Part": row.lcsc_part,
                    "Manufacturer": p.manufacturer if p else row.manufacturer,
                    "Description": row.description,
                    "Stage": row.stage,
                    "Qty": row.qty,
                    "Stock": p.stock if p else "",
                    "Price_USD": f"{p.unit_price:.4f}" if p and p.unit_price else "",
                    "Status": p.status if p else "",
                    "URL": p.url if p else "",
                    "Notes": row.notes,
                })

        print(f"\nRelatorio salvo em: {out}")


# --- CLI ---

def search_mpn(mpn: str, client: LCSCClient):
    """Busca MPN no catálogo LCSC via EasyEDA Pro API e mostra resultados."""
    print(f"Buscando MPN: {mpn} ...\n")
    results = client.search_by_mpn(mpn, top_n=8)

    if not results:
        print("Nenhum resultado encontrado.")
        print(f"Busca manual: https://www.lcsc.com/search?q={mpn}")
        return

    print(f"{'LCSC':<12} {'Fabricante':<20} {'MPN':<30} {'Pacote':<12} {'Stock':>8}  {'Preco':>8}")
    print("-" * 100)
    for r in results:
        label = STATUS_LABELS.get(r.status, "[???]")
        price_str = f"${r.unit_price:.4f}" if r.unit_price else "—"
        print(f"{r.lcsc_part:<12} {r.manufacturer[:19]:<20} {r.mpn[:29]:<30} {r.package[:11]:<12} {r.stock:>8,}  {price_str:>8}  {label}")

    best = results[0]
    print(f"\nMelhor opção: {best.lcsc_part} ({best.manufacturer} {best.mpn})")
    print(f"Stock: {best.stock:,}  Preço: ${best.unit_price:.4f}  Status: {best.status}")
    print(f"URL:   {best.url}")


def resolve_bom_mpns(bom_path: str, client: LCSCClient, output: str = None):
    """Busca LCSC codes para todas as linhas da BOM sem LCSC_Part preenchido."""
    validator = BOMValidator(bom_path)
    empty_rows = [r for r in validator.rows if not r.lcsc_part and r.mpn]

    if not empty_rows:
        print("Todas as linhas já têm LCSC_Part preenchido.")
        return

    print(f"Buscando LCSC codes para {len(empty_rows)} componentes sem código...\n")

    # Lê CSV original para preservar
    bom_path_obj = Path(bom_path)
    with open(bom_path_obj, newline="", encoding="utf-8") as f:
        original_rows = list(csv.DictReader(f))
    fieldnames = list(original_rows[0].keys()) if original_rows else []

    updates: dict[str, str] = {}  # Reference -> LCSC code

    for row in empty_rows:
        print(f"  {row.reference:<12} {row.mpn:<30} -> ", end="", flush=True)
        results = client.search_by_mpn(row.mpn, top_n=3)

        if results:
            best = results[0]
            print(f"{best.lcsc_part}  ({best.manufacturer} {best.mpn})  Stock: {best.stock:,}")
            if best.status in ("in_stock", "low_stock"):
                updates[row.reference] = best.lcsc_part
        else:
            print("não encontrado")

    if not updates:
        print("\nNenhum código encontrado automaticamente.")
        return

    # Salva BOM atualizada
    out_path = output or str(bom_path_obj.parent / (bom_path_obj.stem + "_resolved.csv"))
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in original_rows:
            ref = row.get("Reference", "")
            if ref in updates and not row.get("LCSC_Part", "").strip():
                row["LCSC_Part"] = updates[ref]
            writer.writerow(row)

    print(f"\n{len(updates)} códigos encontrados e salvos em: {out_path}")
    print("Revise o arquivo e renomeie para vcortex_bom.csv se aprovado.")


def check_single_part(lcsc_part: str, client: LCSCClient):
    print(f"Consultando {lcsc_part}...")
    info = client.get_product(lcsc_part)

    print(f"\nPart:          {info.lcsc_part}")
    print(f"Status:        {info.status}")
    print(f"Fabricante:    {info.manufacturer or '—'}")
    print(f"MPN:           {info.mpn or '—'}")
    print(f"Descricao:     {info.description or '—'}")
    print(f"Pacote:        {info.package or '—'}")
    print(f"Estoque:       {info.stock:,}")
    print(f"Preco (qty 1): ${info.unit_price:.4f}" if info.unit_price else "Preco:         —")
    print(f"URL:           {info.url}")
    if info.raw_error:
        print(f"Erro:          {info.raw_error}")


def main():
    parser = argparse.ArgumentParser(
        description="V-Cortex LCSC Stock Checker — verifica disponibilidade da BOM na LCSC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python lcsc_stock_checker.py --bom ../bom/vcortex_bom.csv
  python lcsc_stock_checker.py --bom ../bom/vcortex_bom.csv --stage 1
  python lcsc_stock_checker.py --part C123456
  python lcsc_stock_checker.py --bom ../bom/vcortex_bom.csv --output ../bom/stock_report.csv
        """,
    )
    parser.add_argument("--bom", help="Caminho para o arquivo BOM CSV")
    parser.add_argument("--part", help="Verificar um único part number LCSC (ex: C123456)")
    parser.add_argument("--search", metavar="MPN", help="Buscar componente por MPN no catálogo LCSC")
    parser.add_argument("--resolve-bom", action="store_true",
                        help="Busca LCSC codes para linhas sem LCSC_Part (requer --bom)")
    parser.add_argument("--stage", type=int, help="Filtrar por estágio de prototipagem (1-6)")
    parser.add_argument(
        "--output",
        default=None,
        help="Caminho para salvar relatório CSV",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Segundos entre requests (padrão: {DEFAULT_DELAY})",
    )

    args = parser.parse_args()

    if not any([args.bom, args.part, args.search]):
        parser.error("Informe --bom, --part ou --search")

    client = LCSCClient(rate_limit=args.delay)

    if args.search:
        search_mpn(args.search, client)
        return

    if args.part:
        check_single_part(args.part, client)
        return

    if args.bom:
        bom_path = Path(args.bom)
        if not bom_path.exists():
            print(f"Erro: arquivo nao encontrado: {bom_path}", file=sys.stderr)
            sys.exit(1)

        if args.resolve_bom:
            resolve_bom_mpns(str(bom_path), client, output=args.output)
            return

        validator = BOMValidator(str(bom_path))
        rows = validator.validate(client, stage_filter=args.stage)
        validator.print_summary(rows)

        output = args.output or str(bom_path.parent / "bom_stock_report.csv")
        validator.save_report(rows, output)


if __name__ == "__main__":
    main()
