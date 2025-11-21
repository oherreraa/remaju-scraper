import json
import time
import logging
import re
import os
from datetime import datetime
from typing import Dict, List, Any, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
)

# =========================
# CONFIG
# =========================
BASE_URL = "https://remaju.pj.gob.pe/remaju/"
DEFAULT_TIMEOUT = 25
SCROLL_PAUSE = 1.2
MAX_SCROLLS_PER_PAGE = 12          # for infinite-scroll style loading
MAX_REMATES_PER_RUN = None         # set int to limit, e.g. 20
HEADLESS = os.getenv("HEADLESS", "1") != "0"

# Known label patterns for Detalle extraction (fallback regex)
DETALLE_FIELDS = [
    ("expediente", r"Expediente"),
    ("distrito_judicial", r"Distrito Judicial"),
    ("organo_jurisdiccional", r"(Órgano|Organo) Jurisdiccional"),
    ("instancia", r"Instancia"),
    ("juez", r"Juez"),
    ("especialista", r"Especialista"),
    ("materia", r"Materia"),
    ("resolucion", r"Resoluci[oó]n"),
    ("fecha_resolucion", r"Fecha Resoluci[oó]n"),
    ("archivo_resolucion", r"Archivo"),
    ("convocatoria", r"Convocatoria"),
    ("tasacion", r"Tasaci[oó]n"),
    ("precio_base", r"Precio Base"),
    ("incremento_ofertas", r"Incremento de Ofertas"),
    ("arancel", r"Arancel"),
    ("oblaje", r"Oblaje"),
]

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("scrape_remaju.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("remaju-scraper")


# =========================
# DRIVER
# =========================
def build_driver() -> webdriver.Chrome:
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1440,1000")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--lang=es-PE")
    # reduce bot-detection friction a bit
    opts.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(60)
    return driver


def wait_for_document_ready(driver: webdriver.Chrome, timeout: int = DEFAULT_TIMEOUT):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def safe_screenshot(driver: webdriver.Chrome, name: str):
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"debug_{name}_{ts}.png"
        driver.save_screenshot(path)
        logger.info(f"Saved screenshot: {path}")
    except Exception as e:
        logger.warning(f"Screenshot failed: {e}")


def scroll_into_view(driver: webdriver.Chrome, element):
    driver.execute_script(
        "arguments[0].scrollIntoView({behavior:'instant', block:'center'});",
        element
    )
    time.sleep(0.4)


# =========================
# LIST PAGE HELPERS
# =========================
def locate_cards(driver: webdriver.Chrome) -> List[Any]:
    """
    Tries multiple container patterns because PJ may change DOM.
    We search for blocks containing 'Remate N°' text.
    """
    xpath_candidates = [
        "//mat-card[.//*[contains(.,'Remate N')]]",
        "//div[contains(@class,'mat-card')][.//*[contains(.,'Remate N')]]",
        "//div[contains(@class,'remate') and .//*[contains(.,'Remate N')]]",
        "//div[.//*[contains(.,'Remate N')]]"
    ]
    for xp in xpath_candidates:
        cards = driver.find_elements(By.XPATH, xp)
        if cards:
            return cards
    return []


def load_all_cards(driver: webdriver.Chrome) -> List[Any]:
    """
    Handles infinite scroll: scroll down until no new cards appear.
    """
    last_count = 0
    stable_rounds = 0

    for i in range(MAX_SCROLLS_PER_PAGE):
        cards = locate_cards(driver)
        count = len(cards)

        logger.info(f"Scroll round {i+1}: cards={count}")
        if count == last_count:
            stable_rounds += 1
        else:
            stable_rounds = 0

        if stable_rounds >= 2:
            break

        last_count = count
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_PAUSE)

    return locate_cards(driver)


def parse_card_text(card_text: str) -> Dict[str, Any]:
    """
    Parses the visible summary text from a Remate card.
    """
    data = {}

    # remate number + convocatoria
    m = re.search(r"Remate\s*N[°o]\s*(\d+)\s*-\s*(.*)", card_text, re.IGNORECASE)
    if m:
        data["numero"] = m.group(1).strip()
        data["numero_remate"] = f"Remate N° {m.group(1).strip()} - {m.group(2).strip()}"
        data["tipo_convocatoria"] = m.group(2).strip().split()[0] if m.group(2) else ""
    else:
        m2 = re.search(r"Remate\s*N[°o]\s*(\d+)", card_text, re.IGNORECASE)
        if m2:
            data["numero"] = m2.group(1).strip()
            data["numero_remate"] = f"Remate N° {m2.group(1).strip()}"
        else:
            data["numero"] = ""
            data["numero_remate"] = ""

    # try to find base price on card
    money = re.findall(r"(S\/\.\s*[\d,]+(?:\.\d{2})?|\$\s*[\d,]+(?:\.\d{2})?)", card_text)
    if money:
        data["precio_base"] = money[0].strip()
        data["precio_base_moneda"] = "USD" if "$" in money[0] else "PEN"
        try:
            num = re.sub(r"[^\d.]", "", money[0].replace(",", ""))
            data["precio_base_numerico"] = float(num) if num else None
        except:
            data["precio_base_numerico"] = None
    else:
        data["precio_base"] = ""
        data["precio_base_moneda"] = ""
        data["precio_base_numerico"] = None

    # status block on right
    estado = ""
    for line in card_text.splitlines():
        if "En proceso" in line or "Publica" in line or "Inscrip" in line:
            estado += (line.strip() + " ")
    data["estado"] = estado.strip()

    # preserve raw snippet for traceability
    data["card_text"] = card_text.strip()
    return data


def click_button_in_card(card, label: str) -> bool:
    """
    Clicks a button/link inside a card by visible text.
    """
    try:
        btn = card.find_element(By.XPATH, f".//button[contains(., '{label}')] | .//a[contains(., '{label}')]")
        btn.click()
        return True
    except NoSuchElementException:
        return False
    except Exception:
        return False


# =========================
# SEGUIMIENTO
# =========================
def scrape_seguimiento(driver: webdriver.Chrome, card) -> Dict[str, Any]:
    """
    Opens Seguimiento (modal or route) and captures text.
    """
    seguimiento = {"raw_text": "", "items": []}

    if not click_button_in_card(card, "Seguimiento"):
        return seguimiento

    time.sleep(1.2)

    # modal case (Angular Material dialog)
    dialog_xpath = "//mat-dialog-container | //div[contains(@class,'cdk-overlay-pane')]//mat-dialog-container"
    try:
        dialog = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.XPATH, dialog_xpath))
        )
        raw = dialog.text.strip()
        seguimiento["raw_text"] = raw

        # parse timeline-ish lines into items
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        for l in lines:
            # simplistic: date + event
            md = re.search(r"(\d{2}/\d{2}/\d{4})\s*(.*)", l)
            if md:
                seguimiento["items"].append({
                    "fecha": md.group(1),
                    "evento": md.group(2).strip()
                })

        # close modal: ESC or close button
        try:
            driver.find_element(By.XPATH, "//button[contains(.,'Cerrar')]").click()
        except Exception:
            driver.switch_to.active_element.send_keys(Keys.ESCAPE)

        time.sleep(0.8)
        return seguimiento

    except TimeoutException:
        # route case: wait for a seguimiento title or block
        try:
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(.,'Seguimiento')]"))
            )
            raw = driver.find_element(By.TAG_NAME, "body").text.strip()
            seguimiento["raw_text"] = raw
        except Exception:
            seguimiento["raw_text"] = driver.find_element(By.TAG_NAME, "body").text.strip()

        # go back to list
        safe_back(driver)
        return seguimiento


# =========================
# DETALLE / INMUEBLES / CRONOGRAMA
# =========================
def safe_back(driver: webdriver.Chrome):
    """
    Go back to list with stability.
    """
    driver.back()
    time.sleep(1.2)
    wait_for_document_ready(driver, 15)


def click_tab(driver: webdriver.Chrome, tab_label: str) -> bool:
    """
    Clicks a mat-tab by its visible label.
    """
    try:
        tab = driver.find_element(By.XPATH, f"//div[@role='tab' and contains(., '{tab_label}')]")
        tab.click()
        time.sleep(0.8)
        return True
    except NoSuchElementException:
        return False
    except Exception:
        return False


def extract_from_table(driver: webdriver.Chrome) -> Dict[str, str]:
    """
    Attempts to read 2-column tables (label/value).
    """
    out = {}
    try:
        rows = driver.find_elements(By.XPATH, "//table//tr")
        for r in rows:
            cells = r.find_elements(By.XPATH, ".//th|.//td")
            if len(cells) >= 2:
                k = cells[0].text.strip().strip(":")
                v = cells[1].text.strip()
                if k and v:
                    out[k] = v
    except Exception:
        pass
    return out


def regex_extract_fields(page_text: str) -> Dict[str, str]:
    """
    Fallback: regex over full page text using known labels.
    """
    data = {}

    # normalize spaces
    txt = re.sub(r"[ \t]+", " ", page_text)
    txt_lines = [l.strip() for l in page_text.splitlines() if l.strip()]

    # map line-based "Label: Value"
    line_map = {}
    for l in txt_lines:
        if ":" in l:
            k, v = l.split(":", 1)
            if k.strip() and v.strip():
                line_map[k.strip()] = v.strip()

    # use known DETALLE_FIELDS
    for key, pat in DETALLE_FIELDS:
        val = ""
        # direct line map match
        for lk, lv in line_map.items():
            if re.fullmatch(pat, lk, re.IGNORECASE):
                val = lv
                break
        if not val:
            # same-line regex like "Expediente 1234-2023"
            m = re.search(pat + r"\s*[:\-]?\s*(.+)", txt, re.IGNORECASE)
            if m:
                # cut at next known label if possible
                val = m.group(1).strip()
                # heuristic trimming
                val = val.split(" Distrito Judicial")[0].split(" Órgano")[0].strip()
        data[key] = val

    return data


def scrape_detalle(driver: webdriver.Chrome) -> Dict[str, Any]:
    """
    Scrapes Detalle tab + then Inmuebles and Cronograma tabs.
    """
    detalle_block = {}
    body_text = driver.find_element(By.TAG_NAME, "body").text

    # try structured 2-col table first
    table_kv = extract_from_table(driver)

    # fuse with regex fields
    regex_kv = regex_extract_fields(body_text)

    # map a few known label variants from table_kv into canonical keys
    canon = {}
    label_to_key = {
        "Expediente": "expediente",
        "Distrito Judicial": "distrito_judicial",
        "Órgano Jurisdiccional": "organo_jurisdiccional",
        "Organo Jurisdiccional": "organo_jurisdiccional",
        "Instancia": "instancia",
        "Juez": "juez",
        "Especialista": "especialista",
        "Materia": "materia",
        "Resolución": "resolucion",
        "Resolucion": "resolucion",
        "Fecha Resolución": "fecha_resolucion",
        "Fecha Resolucion": "fecha_resolucion",
        "Archivo": "archivo_resolucion",
        "Convocatoria": "convocatoria",
        "Tasación": "tasacion",
        "Tasacion": "tasacion",
        "Precio Base": "precio_base",
        "Incremento de Ofertas": "incremento_ofertas",
        "Arancel": "arancel",
        "Oblaje": "oblaje",
    }
    for k, v in table_kv.items():
        if k in label_to_key:
            canon[label_to_key[k]] = v

    # merge canon over regex_kv
    detalle_block.update(regex_kv)
    detalle_block.update(canon)

    # Inmuebles (tab is part of Detalle)
    inmuebles = []
    if click_tab(driver, "Inmuebles"):
        inmuebles = scrape_generic_table(driver)

    # Cronograma (tab is part of Detalle)
    cronograma = []
    if click_tab(driver, "Cronograma"):
        cronograma = scrape_generic_table(driver)

    return {
        "detalle": detalle_block,
        "inmuebles": inmuebles,
        "cronograma": cronograma
    }


def scrape_generic_table(driver: webdriver.Chrome) -> List[Dict[str, str]]:
    """
    Scrapes visible table (mat-table or normal table).
    Returns rows with header->cell mapping.
    """
    rows_data = []
    try:
        table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//table | //mat-table"))
        )
        # headers
        headers = []
        header_elems = table.find_elements(By.XPATH, ".//th | .//mat-header-cell")
        for h in header_elems:
            t = h.text.strip()
            if t:
                headers.append(t)

        # rows
        row_elems = table.find_elements(By.XPATH, ".//tr[td] | .//mat-row")
        for r in row_elems:
            cell_elems = r.find_elements(By.XPATH, ".//td | .//mat-cell")
            cells = [c.text.strip() for c in cell_elems]
            if not any(cells):
                continue
            if headers and len(headers) == len(cells):
                rows_data.append({headers[i]: cells[i] for i in range(len(headers))})
            else:
                rows_data.append({f"col_{i+1}": cells[i] for i in range(len(cells))})
    except TimeoutException:
        pass
    except Exception as e:
        logger.warning(f"scrape_generic_table error: {e}")

    return rows_data


def open_detalle_and_scrape(driver: webdriver.Chrome, card) -> Dict[str, Any]:
    if not click_button_in_card(card, "Detalle"):
        return {"detalle": {}, "inmuebles": [], "cronograma": []}

    # wait for Detalle view
    try:
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[contains(.,'Detalle de expediente') or contains(.,'Detalle') or contains(.,'Expediente')]")
            )
        )
    except TimeoutException:
        # still proceed with whatever loaded
        pass

    time.sleep(0.8)
    data = scrape_detalle(driver)

    # return to list
    safe_back(driver)
    return data


# =========================
# MAIN SCRAPE
# =========================
def scrape_remaju() -> List[Dict[str, Any]]:
    driver = build_driver()
    remates: List[Dict[str, Any]] = []
    output_path = None

    try:
        logger.info(f"Opening {BASE_URL}")
        driver.get(BASE_URL)
        wait_for_document_ready(driver)

        # wait for any remate cards to exist
        WebDriverWait(driver, DEFAULT_TIMEOUT).until(
            lambda d: len(locate_cards(d)) > 0
        )

        cards = load_all_cards(driver)
        logger.info(f"Total cards detected: {len(cards)}")

        n_cards = len(cards)
        limit = MAX_REMATES_PER_RUN if MAX_REMATES_PER_RUN else n_cards

        for idx in range(limit):
            # refresh cards each loop to avoid stale elements after back()
            cards = locate_cards(driver)
            if idx >= len(cards):
                break

            card = cards[idx]
            scroll_into_view(driver, card)

            text = card.text
            base_data = parse_card_text(text)
            base_data["row_index"] = idx
            base_data["line_index"] = None  # kept for compatibility with your original output

            logger.info(f"[{idx+1}/{limit}] Remate {base_data.get('numero')}")

            # Seguimiento module
            try:
                base_data["seguimiento"] = scrape_seguimiento(driver, card)
            except Exception as e:
                logger.warning(f"Seguimiento failed idx={idx}: {e}")
                base_data["seguimiento"] = {"raw_text": "", "items": []}

            # Detalle + Inmuebles + Cronograma
            try:
                detail_pack = open_detalle_and_scrape(driver, card)
                # merge hierarchical blocks
                base_data.update(detail_pack["detalle"])
                base_data["inmuebles"] = detail_pack["inmuebles"]
                base_data["cronograma"] = detail_pack["cronograma"]
            except Exception as e:
                logger.error(f"Detalle scraping failed idx={idx}: {e}")
                safe_screenshot(driver, f"detalle_fail_{idx}")
                # best-effort go back
                try:
                    safe_back(driver)
                except Exception:
                    pass

            remates.append(base_data)

    except Exception as e:
        logger.error(f"Fatal scrape error: {e}")
        safe_screenshot(driver, "fatal")
    finally:
        # Always write what we have
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"remates_{ts}.json"
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump({"remates": remates}, f, ensure_ascii=False, indent=2)
            logger.info(f"JSON saved: {output_path}")
        except Exception as e:
            logger.error(f"Could not write JSON output: {e}")
        try:
            driver.quit()
        except Exception:
            pass

    return remates


if __name__ == "__main__":
    data = scrape_remaju()
    print(f"\nDone. Remates scraped: {len(data)}")
