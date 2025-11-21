import json
import time
import logging
import re
import argparse
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


BASE_URL = "https://remaju.pj.gob.pe/remaju"
REMATES_URL = f"{BASE_URL}/#/remates"  # en móvil se ve /remaju; esta ruta suele renderizar el módulo de remates


# ----------------------------
# Configuración de logging
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("remaju-scraper")


# ----------------------------
# Helpers generales
# ----------------------------
def setup_driver(headless: bool = True, window_size: str = "1920,1080") -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument(f"--window-size={window_size}")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=es-PE")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    return driver


def wait_visible(driver, by, value, timeout=25):
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((by, value))
    )


def wait_clickable(driver, by, value, timeout=25):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, value))
    )


def safe_find(driver, by, value, timeout=6):
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
    except Exception:
        return None


def safe_find_all(driver, by, value, timeout=6):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
        return driver.find_elements(by, value)
    except Exception:
        return []


def safe_text(el) -> Optional[str]:
    if not el:
        return None
    txt = el.text.strip()
    return txt if txt else None


def normalize_whitespace(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s if s else None


def parse_money(text: Optional[str]) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """
    Devuelve: (valor_numerico, moneda, texto_original)
    Ej.: "$ 140,952.00" -> (140952.0, "USD", "$ 140,952.00")
         "S/ 5,000.00" -> (5000.0, "PEN", "S/ 5,000.00")
    """
    if not text:
        return None, None, None

    raw = text.strip()
    moneda = None
    if "$" in raw:
        moneda = "USD"
    elif "S/" in raw or "S/." in raw:
        moneda = "PEN"

    num = None
    m = re.search(r"([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)", raw)
    if m:
        num_str = m.group(1)
        # normaliza a formato float con punto decimal
        num_str = num_str.replace(",", "")
        try:
            num = float(num_str)
        except Exception:
            num = None

    return num, moneda, raw


def click_tab_by_text(driver, tab_text: str, timeout=10) -> bool:
    """
    Clic en pestaña superior (Remate / Inmuebles / Cronograma).
    """
    xpath = f"//a[normalize-space()='{tab_text}'] | //li/a[normalize-space()='{tab_text}']"
    tab = safe_find(driver, By.XPATH, xpath, timeout=timeout)
    if not tab:
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab)
        tab.click()
        time.sleep(0.5)
        return True
    except Exception:
        return False


def value_by_label(driver, label: str) -> Optional[str]:
    """
    Busca un label específico en la vista actual y retorna el valor asociado
    usando varios patrones de XPath para tolerancia a cambios leves.
    """
    label = label.strip()

    xpaths = [
        # patrón label -> siguiente td
        f"//*[normalize-space()='{label}']/following::td[1]",
        f"//td[normalize-space()='{label}']/following-sibling::td[1]",
        # patrón label dentro de div -> siguiente div/p/span
        f"//*[self::label or self::span][normalize-space()='{label}']/following-sibling::*[1]",
        f"//*[contains(normalize-space(),'{label}')]/following-sibling::*[1]",
        # patrón lista descriptiva
        f"//*[normalize-space()='{label}']/following::p[1]",
    ]

    for xp in xpaths:
        el = safe_find(driver, By.XPATH, xp, timeout=2)
        txt = safe_text(el)
        if txt:
            return normalize_whitespace(txt)

    return None


def wait_for_user_captcha():
    """
    El portal tiene CAPTCHA para aplicar filtros.
    Si corres headless probablemente no podrás resolverlo.
    En modo no-headless, resuélvelo manualmente y presiona Enter.
    """
    input("\nResuelve el CAPTCHA y aplica filtros en el navegador. Luego presiona Enter aquí para continuar...\n")


# ----------------------------
# Extracción por módulos
# ----------------------------
def extract_remate_tab(driver) -> Dict[str, Any]:
    """
    Extrae el tab 'Remate' (campos principales del remate).
    """
    click_tab_by_text(driver, "Remate")

    fields_map = {
        "expediente": "Expediente",
        "distrito_judicial": "Distrito Judicial",
        "organo_jurisdiccional": "Órgano Jurisdiccional",
        "instancia": "Instancia",
        "juez": "Juez",
        "especialista": "Especialista",
        "materia": "Materia",
        "resolucion": "Resolución",
        "fecha_resolucion": "Fecha Resolución",
        "archivo_resolucion": "Archivo",
        "convocatoria": "Convocatoria",
        "tipo_cambio": "Tipo Cambio",
        "tasacion": "Tasación",
        "precio_base": "Precio Base",
        "incremento_ofertas": "Incremento entre ofertas",
        "arancel": "Arancel",
        "oblaje": "Oblaje",
        "descripcion_completa": "Descripción",
        "num_inscrito": "N° inscrito",
    }

    data = {}
    for key, label in fields_map.items():
        data[key] = value_by_label(driver, label)

    # parseos derivados
    precio_num, precio_moneda, precio_raw = parse_money(data.get("precio_base"))
    data["precio_base"] = precio_raw
    data["precio_base_numerico"] = precio_num
    data["precio_base_moneda"] = precio_moneda

    tas_num, tas_moneda, tas_raw = parse_money(data.get("tasacion"))
    data["tasacion"] = tas_raw
    data["tasacion_numerico"] = tas_num
    data["tasacion_moneda"] = tas_moneda

    # tipo cambio float
    if data.get("tipo_cambio"):
        try:
            data["tipo_cambio_numerico"] = float(
                re.sub(r"[^\d.]", "", data["tipo_cambio"].replace(",", "."))
            )
        except Exception:
            data["tipo_cambio_numerico"] = None
    else:
        data["tipo_cambio_numerico"] = None

    return data


def extract_seguimiento_panel(driver) -> Dict[str, Any]:
    """
    Extrae el panel 'DETALLE DE SEGUIMIENTO' que aparece dentro de la vista de detalle.
    """
    click_tab_by_text(driver, "Remate")  # el panel está en este tab

    seguimiento = {
        "numero_convocatoria": value_by_label(driver, "N° Convocatoria"),
        "fecha_registro": value_by_label(driver, "Fecha de registro"),
        "procesado_por": value_by_label(driver, "Procesado por"),
        "rematado": value_by_label(driver, "Rematado?"),
        "fase_convocatoria": value_by_label(driver, "Fase convocatoria"),
        "estado_convocatoria": value_by_label(driver, "Estado convocatoria"),
    }
    return seguimiento


def extract_inmuebles_tab(driver) -> List[Dict[str, Any]]:
    """
    Extrae la tabla del tab 'Inmuebles'.
    """
    ok = click_tab_by_text(driver, "Inmuebles")
    if not ok:
        return []

    # cabecera superior (a veces trae distrito/departamento/provincia)
    distrito = value_by_label(driver, "Distrito Judicial") or value_by_label(driver, "Distrito")
    departamento = value_by_label(driver, "Departamento")
    provincia = value_by_label(driver, "Provincia")

    # tabla de inmuebles
    rows = safe_find_all(driver, By.XPATH, "//table//tbody/tr", timeout=5)
    inmuebles = []

    for i, r in enumerate(rows):
        cols = r.find_elements(By.XPATH, "./td")
        # orden típico según screenshot:
        # 0 Partida Registral | 1 Tipo Inmueble | 2 Dirección | 3 Carga y/o Gravamen
        # 4 % Rematar | 5 Márgenes
        def col_text(idx):
            try:
                return normalize_whitespace(cols[idx].text)
            except Exception:
                return None

        inmueble = {
            "row_index": i,
            "distrito": distrito,
            "departamento": departamento,
            "provincia": provincia,
            "partida_registral": col_text(0),
            "tipo_inmueble": col_text(1),
            "direccion": col_text(2),
            "carga_gravamen": col_text(3),
            "porcentaje_rematar": col_text(4),
            "margenes": col_text(5),
        }
        inmuebles.append(inmueble)

    return inmuebles


def extract_cronograma_tab(driver) -> Dict[str, Any]:
    """
    Extrae el tab 'Cronograma'. La UI suele mostrar fechas/horas del remate.
    """
    ok = click_tab_by_text(driver, "Cronograma")
    if not ok:
        return {}

    # si hay tabla:
    rows = safe_find_all(driver, By.XPATH, "//table//tbody/tr", timeout=4)
    if rows:
        eventos = []
        for i, r in enumerate(rows):
            cols = r.find_elements(By.XPATH, "./td")
            eventos.append({
                "row_index": i,
                "descripcion": normalize_whitespace(cols[0].text) if len(cols) > 0 else None,
                "fecha": normalize_whitespace(cols[1].text) if len(cols) > 1 else None,
                "hora": normalize_whitespace(cols[2].text) if len(cols) > 2 else None,
                "observacion": normalize_whitespace(cols[3].text) if len(cols) > 3 else None,
            })
        return {"eventos": eventos}

    # si no hay tabla, usa labels comunes:
    cronograma = {
        "fecha_remate": value_by_label(driver, "Fecha de remate") or value_by_label(driver, "Fecha"),
        "hora_remate": value_by_label(driver, "Hora de remate") or value_by_label(driver, "Hora"),
        "lugar": value_by_label(driver, "Lugar") or value_by_label(driver, "Dirección"),
        "observaciones": value_by_label(driver, "Observaciones"),
    }
    return cr
