import json
import time
import logging
import re
import os
import unicodedata
import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# =========================
# CONFIG
# =========================
BASE_URL = "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml"
WAIT_TIMEOUT = int(os.getenv("WAIT_TIMEOUT", "30"))
MAX_PAGES = int(os.getenv("MAX_PAGES", "50"))
HEADLESS = os.getenv("HEADLESS", "1") != "0"
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("remaju-scraper")


# =========================
# UTILS
# =========================
def ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def save_screenshot(driver, label: str) -> str:
    path = os.path.join(OUTPUT_DIR, f"{label}_{ts()}.png")
    try:
        driver.save_screenshot(path)
        log.info(f"Saved screenshot: {path}")
    except Exception as e:
        log.error(f"Could not save screenshot: {e}")
    return path


def dump_json(data: Any, label: str) -> str:
    path = os.path.join(OUTPUT_DIR, f"{label}_{ts()}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log.info(f"JSON saved: {path}")
    except Exception as e:
        log.error(f"Could not save JSON: {e}")
    return path


def norm(s: str) -> str:
    """Normalize label text for matching."""
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s)
    s = s.replace(":", "")
    return s


def safe_text(el) -> str:
    try:
        return el.text.strip()
    except Exception:
        return ""


def parse_money(raw: str) -> Dict[str, Any]:
    """
    Parse a money string like:
      "S/. 33,481.17" or "$ 140,952.00"
    """
    out = {"texto": raw, "moneda": None, "numerico": None}
    if not raw:
        return out

    raw_clean = raw.strip()
    if "S/." in raw_clean or "S/" in raw_clean:
        out["moneda"] = "PEN"
    elif "$" in raw_clean or "USD" in raw_clean:
        out["moneda"] = "USD"

    m = re.search(r"([0-9][0-9\.,]*)", raw_clean)
    if m:
        num_str = m.group(1).replace(",", "")
        try:
            out["numerico"] = float(num_str)
        except ValueError:
            out["numerico"] = None

    return out


def wait_doc_ready(driver, timeout=WAIT_TIMEOUT):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


# =========================
# DRIVER
# =========================
def build_driver() -> webdriver.Chrome:
    options = Options()

    if HEADLESS:
        options.add_argument("--headless=new")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=es-ES")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Allow custom chrome binary if GH runner path differs
    chrome_bin = os.getenv("CHROME_BINARY")
    if chrome_bin:
        options.binary_location = chrome_bin

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(WAIT_TIMEOUT)
    return driver


# =========================
# PAGE OPEN / SEARCH CLICK
# =========================
def open_base(driver):
    log.info(f"Opening {BASE_URL}")
    driver.get(BASE_URL)
    wait_doc_ready(driver)

    # If there is a cookie/consent dialog, attempt to accept
    try:
        consent_btns = driver.find_elements(
            By.XPATH,
            "//button[contains(.,'Aceptar') or contains(.,'aceptar') or contains(.,'OK')]"
        )
        if consent_btns:
            driver.execute_script("arguments[0].click();", consent_btns[0])
            time.sleep(1)
    except Exception:
        pass

    # Click Buscar / Consultar if present (PrimeFaces often needs explicit query)
    try:
        buscar = driver.find_elements(
            By.XPATH,
            "//a[contains(.,'Buscar') or contains(.,'Consultar') or contains(.,'Filtrar')]"
        )
        if buscar:
            log.info("Clicking Buscar/Consultar to load results...")
            driver.execute_script("arguments[0].click();", buscar[0])
            time.sleep(2)
            wait_doc_ready(driver)
    except Exception as e:
        log.warning(f"Buscar button not clicked (non-fatal): {e}")


# =========================
# LIST DISCOVERY
# =========================
def _candidate_cards(driver) -> List[Any]:
    selectors = [
        (By.CSS_SELECTOR, "div.ui-datascroller-item"),
        (By.CSS_SELECTOR, "div[class*='remate']"),
        (By.CSS_SELECTOR, "table[id*='tabla'] tbody tr"),
        (By.XPATH, "//div[contains(.,'Remate N') and (contains(.,'CONVOCATORIA') or contains(.,'convocatoria'))]"),
    ]

    best: List[Any] = []
    for by, sel in selectors:
        try:
            elems = driver.find_elements(by, sel)
            filtered = []
            for e in elems:
                t = safe_text(e)
                if "Remate N" in t and "CONVOCATORIA" in t.upper():
                    filtered.append(e)
            if len(filtered) > len(best):
                best = filtered
        except Exception:
            continue
    return best


def get_cards(driver) -> List[Any]:
    cards = _candidate_cards(driver)
    if not cards:
        # fallback: sometimes content is in panels
        try:
            panels = driver.find_elements(By.CSS_SELECTOR, "div.ui-panel")
            cards = [p for p in panels if "Remate N" in safe_text(p)]
        except Exception:
            cards = []
    return cards


# =========================
# PARSING LIST CARD
# =========================
def parse_card_text(card_text: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "numero": "",
        "numero_remate": "",
        "tipo_convocatoria": "",
        "precio_base": "",
        "precio_base_numerico": None,
        "precio_base_moneda": "",
        "descripcion_corta": "",
    }

    lines = [l.strip() for l in card_text.splitlines() if l.strip()]

    # Numero remate
    m = re.search(r"Remate\s*N[°º]?\s*(\d+)", card_text, re.IGNORECASE)
    if m:
        data["numero"] = m.group(1)

    # Numero remate line
    for l in lines:
        if re.search(r"Remate\s*N[°º]", l, re.IGNORECASE):
            data["numero_remate"] = l
            break

    # Tipo convocatoria
    if "PRIMERA CONVOCATORIA" in card_text.upper():
        data["tipo_convocatoria"] = "PRIMERA"
    elif "SEGUNDA CONVOCATORIA" in card_text.upper():
        data["tipo_convocatoria"] = "SEGUNDA"
    else:
        data["tipo_convocatoria"] = ""

    # Precio base
    price_line = ""
    for l in lines:
        if "precio" in l.lower() and ("base" in l.lower() or "postor" in l.lower()):
            price_line = l
            break
    if not price_line:
        # fallback first currency in card
        m2 = re.search(r"(S\/\.|\$)\s*[0-9][0-9\.,]*", card_text)
        price_line = m2.group(0) if m2 else ""

    data["precio_base"] = price_line
    money = parse_money(price_line)
    data["precio_base_numerico"] = money["numerico"]
    data["precio_base_moneda"] = money["moneda"] or ""

    # Short description
    if lines:
        data["descripcion_corta"] = " | ".join(lines[:3])[:300]

    return data


def click_detalle_in_card(driver, card) -> bool:
    """
    Try to open detail view from list card.
    Returns True if navigation happened.
    """
    try:
        detalle_links = card.find_elements(
            By.XPATH,
            ".//a[contains(.,'Detalle') or contains(@title,'Detalle') or contains(@aria-label,'Detalle')]"
        )
        if detalle_links:
            old_url = driver.current_url
            driver.execute_script("arguments[0].click();", detalle_links[0])
            time.sleep(1.5)
            wait_doc_ready(driver)
            return driver.current_url != old_url
    except Exception:
        pass

    # Fallback: click any link inside card that looks like navigation
    try:
        any_links = card.find_elements(By.XPATH, ".//a")
        for a in any_links:
            t = safe_text(a).upper()
            if "DETALLE" in t or "VER" in t:
                old_url = driver.current_url
                driver.execute_script("arguments[0].click();", a)
                time.sleep(1.5)
                wait_doc_ready(driver)
                return driver.current_url != old_url
    except Exception:
        pass

    return False


# =========================
# DETAIL PARSING
# =========================
LABEL_MAP = {
    "expediente": "expediente",
    "distrito judicial": "distrito_judicial",
    "organo jurisdiccional": "organo_jurisdiccional",
    "instancia": "instancia",
    "juez": "juez",
    "especialista": "especialista",
    "materia": "materia",
    "resolucion": "resolucion",
    "fecha resolucion": "fecha_resolucion",
    "tasacion": "tasacion",
    "precio base": "precio_base",
    "incremento ofertas": "incremento_ofertas",
    "tipo cambio": "tipo_cambio",
    "arancel": "arancel",
    "oblaje": "oblaje",
    "convocatoria": "convocatoria",
}


def parse_label_value_tables(driver) -> Dict[str, str]:
    pairs: Dict[str, str] = {}
    rows = driver.find_elements(By.XPATH, "//table//tr[td and count(td)>=2]")
    for r in rows:
        tds = r.find_elements(By.XPATH, "./td")
        if len(tds) < 2:
            continue
        label = norm(safe_text(tds[0]))
        value = safe_text(tds[1])
        if label and value and label not in pairs:
            pairs[label] = value
    return pairs


def click_tab_if_exists(driver, tab_keywords: List[str]) -> bool:
    """
    Click a PrimeFaces tab by matching visible text.
    """
    for kw in tab_keywords:
        try:
            tabs = driver.find_elements(
                By.XPATH,
                f"//a[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÜÑ','abcdefghijklmnopqrstuvwxyzáéíóúüñ'), '{kw.lower()}')]"
            )
            if tabs:
                driver.execute_script("arguments[0].click();", tabs[0])
                time.sleep(1.2)
                wait_doc_ready(driver)
                return True
        except Exception:
            continue
    return False


def parse_table_as_dicts(driver) -> List[Dict[str, str]]:
    tables = driver.find_elements(By.XPATH, "//table")
    best_rows: List[Dict[str, str]] = []

    for table in tables:
        try:
            headers = table.find_elements(By.XPATH, ".//th")
            if not headers:
                continue
            header_txt = [norm(safe_text(h)) for h in headers]
            body_rows = table.find_elements(By.XPATH, ".//tbody/tr")
            if not body_rows:
                continue

            rows_out = []
            for tr in body_rows:
                tds = tr.find_elements(By.XPATH, "./td")
                if not tds:
                    continue
                cells = [safe_text(td) for td in tds]
                row_d = {}
                for i, c in enumerate(cells):
                    key = header_txt[i] if i < len(header_txt) else f"col_{i+1}"
                    row_d[key] = c
                # consider non-empty rows only
                if any(v.strip() for v in row_d.values()):
                    rows_out.append(row_d)

            if len(rows_out) > len(best_rows):
                best_rows = rows_out
        except Exception:
            continue

    return best_rows


def parse_detalle_page(driver) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Returns:
      detalle_general, inmuebles_list, cronograma_list
    """
    detalle_general: Dict[str, Any] = {}
    inmuebles: List[Dict[str, Any]] = []
    cronograma: List[Dict[str, Any]] = []

    # General label-value pairs
    pairs = parse_label_value_tables(driver)
    otros = {}
    for lbl, val in pairs.items():
        key = LABEL_MAP.get(lbl)
        if key:
            detalle_general[key] = val
        else:
            otros[lbl] = val
    if otros:
        detalle_general["otros_campos"] = otros

    # Inmuebles tab/table
    if click_tab_if_exists(driver, ["inmuebles", "bienes", "inmueble"]):
        inmuebles = parse_table_as_dicts(driver)

    # Cronograma tab/table
    if click_tab_if_exists(driver, ["cronograma", "fechas"]):
        cronograma = parse_table_as_dicts(driver)

    return detalle_general, {"inmuebles": inmuebles}, {"cronograma": cronograma}


def parse_seguimiento(driver) -> Dict[str, Any]:
    """
    Extract seguimiento module if exposed as a tab or panel.
    """
    seguimiento: Dict[str, Any] = {}

    if click_tab_if_exists(driver, ["seguimiento"]):
        pairs = parse_label_value_tables(driver)
        for lbl, val in pairs.items():
            seguimiento[lbl] = val
        seguimiento["tab_visible"] = True
    else:
        seguimiento["tab_visible"] = False

    return seguimiento


def go_back_to_list(driver):
    # Try to click "Regresar/Volver"
    try:
        back_btns = driver.find_elements(
            By.XPATH,
            "//a[contains(.,'Regresar') or contains(.,'Volver') or contains(.,'Retornar') or contains(.,'Atrás')]"
        )
        if back_btns:
            driver.execute_script("arguments[0].click();", back_btns[0])
            time.sleep(1.5)
            wait_doc_ready(driver)
            return
    except Exception:
        pass

    # Fallback browser back
    driver.back()
    time.sleep(1.5)
    wait_doc_ready(driver)


# =========================
# PAGINATION
# =========================
def click_next_page(driver, current_first_text: str) -> bool:
    """
    Attempts to advance paginator / datascroller.
    Returns True if page advanced.
    """
    candidates = []

    # PrimeFaces paginator
    candidates += driver.find_elements(By.CSS_SELECTOR, "a.ui-paginator-next")
    # Text-based
    candidates += driver.find_elements(
        By.XPATH,
        "//a[contains(.,'Siguiente') or contains(.,'Next') or contains(.,'›') or contains(.,'»') or contains(@aria-label,'Next')]"
    )
    # Datascroller "Cargar más"
    candidates += driver.find_elements(
        By.XPATH,
        "//a[contains(.,'Cargar más') or contains(.,'Más resultados') or contains(.,'Ver más')]"
    )

    # Filter duplicates
    uniq = []
    seen = set()
    for c in candidates:
        key = safe_text(c) + (c.get_attribute("class") or "")
        if key not in seen:
            uniq.append(c)
            seen.add(key)

    for btn in uniq:
        try:
            cls = (btn.get_attribute("class") or "").lower()
            if "disabled" in cls:
                continue
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(2)
            wait_doc_ready(driver)
            new_cards = get_cards(driver)
            if new_cards and safe_text(new_cards[0]) != current_first_text:
                return True
        except Exception:
            continue

    return False


# =========================
# MAIN SCRAPE
# =========================
def scrape() -> List[Dict[str, Any]]:
    driver = build_driver()
    results: List[Dict[str, Any]] = []
    seen_numbers = set()

    try:
        open_base(driver)

        for page_idx in range(MAX_PAGES):
            cards = get_cards(driver)
            if not cards:
                log.warning("No cards found on current page.")
                break

            first_txt = safe_text(cards[0])

            log.info(f"Page {page_idx+1}: cards detected = {len(cards)}")

            for card in cards:
                card_text = safe_text(card)
                card_data = parse_card_text(card_text)

                numero = card_data.get("numero") or ""
                if numero and numero in seen_numbers:
                    continue

                # Navigate to detail
                navigated = click_detalle_in_card(driver, card)

                if not navigated:
                    log.warning(f"Could not navigate to detalle for remate {numero or '[sin numero]'}")
                    results.append({
                        **card_data,
                        "detalle": {"detalle_general": {}, "inmuebles": [], "cronograma": []},
                        "seguimiento": {}
                    })
                    if numero:
                        seen_numbers.add(numero)
                    continue

                # Detail page parse
                try:
                    detalle_general, inm, cro = parse_detalle_page(driver)
                    seguimiento = parse_seguimiento(driver)
                except Exception as e:
                    log.error(f"Error parsing detail for remate {numero}: {e}")
                    save_screenshot(driver, f"debug_detalle_{numero or 'sn'}")
                    detalle_general, inm, cro, seguimiento = {}, {"inmuebles": []}, {"cronograma": []}, {}

                # Build final object, preserving your new organization
                remate_obj = {
                    **card_data,
                    "detalle": {
                        "detalle_general": detalle_general,
                        "inmuebles": inm.get("inmuebles", []),
                        "cronograma": cro.get("cronograma", []),
                    },
                    "seguimiento": seguimiento,
                }

                results.append(remate_obj)
                if numero:
                    seen_numbers.add(numero)

                # Return to list
                go_back_to_list(driver)

            # Next page
            advanced = click_next_page(driver, first_txt)
            if not advanced:
                log.info("No next page detected; stopping.")
                break

        return results

    except Exception as e:
        log.error(f"Fatal scrape error: {e}")
        log.error(traceback.format_exc())
        save_screenshot(driver, "debug_fatal")
        raise

    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    log.info("🚀 Iniciando scraping...")
    try:
        remates = scrape()
        dump_json(remates, "remates")
        log.info(f"Done. Remates scraped: {len(remates)}")
    except Exception:
        # Ensure at least an empty file exists for CI artifacts
        dump_json([], "remates_empty")
        log.error("Scraping failed.")
        raise
    log.info("✅ Scraping completado")
