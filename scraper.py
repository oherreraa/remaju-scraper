import json
import time
import logging
import re
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ---------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REMATE_REGEX = re.compile(r"remate\s+n[°º]?\s*(\d+)", re.IGNORECASE)

DETALLE_XPATH = (
    "//button[normalize-space(.)='Detalle']"
    " | //a[normalize-space(.)='Detalle']"
    " | //input[@value='Detalle']"
)


# ---------------------------------------------------------
# DRIVER
# ---------------------------------------------------------

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1366,768")

    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-web-security")

    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko)"
    )

    driver = webdriver.Chrome(options=chrome_options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


# ---------------------------------------------------------
# HELPERS GENERALES
# ---------------------------------------------------------

def extract_value_from_lines(lines, labels):
    """
    Busca una de las etiquetas en 'labels' dentro de las líneas de texto y devuelve el valor
    que esté:
      - en la misma línea (después de la etiqueta), o
      - en la línea siguiente si la línea de la etiqueta no tiene valor.
    """
    for i, line in enumerate(lines):
        low = line.lower()
        for lbl in labels:
            lbl_low = lbl.lower()
            if lbl_low in low:
                # valor en la misma línea
                idx = low.find(lbl_low)
                after = line[idx + len(lbl):].strip(" :\t-")
                if after:
                    return after
                # si no hay valor en la misma línea, tomar la siguiente
                if i + 1 < len(lines):
                    return lines[i + 1].strip()
    return ""


# ---------------------------------------------------------
# PESTAÑA REMATE
# ---------------------------------------------------------

def extract_remate_tab_info(driver):
    """Extraer información de la pestaña REMATE (robusto a variaciones de formato)."""
    remate_data = {
        "expediente": "",
        "distrito_judicial": "",
        "organo_jurisdiccional": "",
        "instancia": "",
        "juez": "",
        "especialista": "",
        "materia": "",
        "resolucion": "",
        "fecha_resolucion": "",
        "archivo_resolucion": "",
        "convocatoria": "",
        "tipo_cambio": "",
        "tasacion": "",
        "precio_base": "",
        "precio_base_numerico": 0.0,
        "precio_base_moneda": "",
        "incremento_ofertas": "",
        "arancel": "",
        "oblaje": "",
        "descripcion_completa": "",
        "num_inscritos": "",
    }

    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [l.strip() for l in page_text.split("\n") if l.strip()]

        # Campos texto simples
        remate_data["expediente"] = extract_value_from_lines(
            lines, ["Expediente"]
        )
        remate_data["distrito_judicial"] = extract_value_from_lines(
            lines, ["Distrito Judicial"]
        )
        remate_data["organo_jurisdiccional"] = extract_value_from_lines(
            lines,
            [
                "Órgano Jurisdisccional",
                "Órgano Jurisdiccional",
                "Organo Jurisdisccional",
                "Organo Jurisdiccional",
                "Organo Juris",
            ],
        )
        remate_data["instancia"] = extract_value_from_lines(
            lines, ["Instancia"]
        )
        remate_data["juez"] = extract_value_from_lines(
            lines, ["Juez"]
        )
        remate_data["especialista"] = extract_value_from_lines(
            lines, ["Especialista"]
        )
        remate_data["materia"] = extract_value_from_lines(
            lines, ["Materia"]
        )
        remate_data["resolucion"] = extract_value_from_lines(
            lines, ["Resolución"]
        )
        remate_data["fecha_resolucion"] = extract_value_from_lines(
            lines, ["Fecha Resolución", "Fecha de Resolución"]
        )
        remate_data["archivo_resolucion"] = extract_value_from_lines(
            lines, ["Archivo", "Archivo Resolución"]
        )
        remate_data["convocatoria"] = extract_value_from_lines(
            lines, ["Convocatoria"]
        )
        remate_data["tipo_cambio"] = extract_value_from_lines(
            lines, ["Tipo Cambio"]
        )
        remate_data["tasacion"] = extract_value_from_lines(
            lines, ["Tasación"]
        )
        remate_data["incremento_ofertas"] = extract_value_from_lines(
            lines, ["Incremento entre ofertas", "Incremento entre Ofertas"]
        )
        remate_data["arancel"] = extract_value_from_lines(
            lines, ["Arancel"]
        )
        remate_data["oblaje"] = extract_value_from_lines(
            lines, ["Oblaje"]
        )
        remate_data["descripcion_completa"] = extract_value_from_lines(
            lines, ["Descripción"]
        )
        remate_data["num_inscritos"] = extract_value_from_lines(
            lines,
            ["N° inscritos", "N° Inscritos", "Nº inscritos", "Nº Inscritos"],
        )

        # Precio base: texto, monto y moneda
        precio = extract_value_from_lines(lines, ["Precio Base"])
        remate_data["precio_base"] = precio

        if precio:
            txt = precio.replace(",", "")
            nums = re.findall(r"\d+\.?\d*", txt)

            if "$" in precio:
                remate_data["precio_base_moneda"] = "USD"
            elif "S/" in precio or "S/." in precio:
                remate_data["precio_base_moneda"] = "PEN"

            if nums:
                try:
                    remate_data["precio_base_numerico"] = float(nums[0])
                except Exception:
                    pass

        logger.info(
            f"✅ Pestaña REMATE: Expediente {remate_data['expediente']}, "
            f"Precio {remate_data['precio_base']}"
        )

    except Exception as e:
        logger.error(f"Error en extract_remate_tab_info: {e}")

    return remate_data


# ---------------------------------------------------------
# PESTAÑA INMUEBLES
# ---------------------------------------------------------

def extract_inmuebles_tab_info(driver):
    """Extraer información de la pestaña INMUEBLES, incluyendo dirección y gravámenes."""
    inmuebles_data = {
        "inmueble_distrito_judicial": "",
        "inmueble_departamento": "",
        "inmueble_provincia": "",
        "inmueble_distrito": "",
        "inmueble_partida_registral": "",
        "inmueble_tipo": "",
        "inmueble_direccion": "",
        "inmueble_cargas_gravamenes": "",
        "inmueble_porcentaje_rematar": "",
        "inmueble_imagenes": "",
    }

    try:
        # Ir a pestaña Inmuebles
        try:
            inmuebles_tab = driver.find_element(
                By.XPATH,
                "//a[contains(., 'Inmuebles') or contains(@href, 'inmuebles') "
                "or contains(@onclick, 'inmuebles')]",
            )
            driver.execute_script("arguments[0].click();", inmuebles_tab)
            time.sleep(2)
            logger.info("✅ Navegó a pestaña Inmuebles")
        except Exception:
            logger.warning("⚠️ No se pudo hacer clic en pestaña Inmuebles")

        body_elem = driver.find_element(By.TAG_NAME, "body")
        page_text = body_elem.text
        lines = [l.strip() for l in page_text.split("\n") if l.strip()]

        # Campos generales encima de la tabla
        inmuebles_data["inmueble_distrito_judicial"] = extract_value_from_lines(
            lines, ["Distrito Judicial"]
        )
        inmuebles_data["inmueble_departamento"] = extract_value_from_lines(
            lines, ["Departamento"]
        )
        inmuebles_data["inmueble_provincia"] = extract_value_from_lines(
            lines, ["Provincia"]
        )
        inmuebles_data["inmueble_distrito"] = extract_value_from_lines(
            lines, ["Distrito"]
        )

        # Tabla principal con Partida, Tipo, Dirección, Carga/Gravamen, Porcentaje, Imágenes
        try:
            tables = body_elem.find_elements(By.TAG_NAME, "table")
            target_table = None
            for t in tables:
                if "Partida Registral" in t.text or "Partida" in t.text:
                    target_table = t
                    break

            if target_table:
                rows = target_table.find_elements(By.XPATH, ".//tbody/tr")
                if rows:
                    # Tomamos la primera fila de datos (un solo inmueble por remate)
                    first_row = rows[0]
                    cells = first_row.find_elements(By.XPATH, ".//td")
                    # Orden esperado:
                    # 0: Partida Registral
                    # 1: Tipo Inmueble
                    # 2: Dirección
                    # 3: Carga y/o Gravamen
                    # 4: Porcentaje a Rematar
                    # 5: Imágenes (si existe)

                    if len(cells) >= 1:
                        inmuebles_data["inmueble_partida_registral"] = cells[0].text.strip()
                    if len(cells) >= 2:
                        inmuebles_data["inmueble_tipo"] = cells[1].text.strip()
                    if len(cells) >= 3:
                        inmuebles_data["inmueble_direccion"] = cells[2].text.strip()
                    if len(cells) >= 4:
                        inmuebles_data["inmueble_cargas_gravamenes"] = cells[3].text.strip()
                    if len(cells) >= 5:
                        inmuebles_data["inmueble_porcentaje_rematar"] = cells[4].text.strip()
                    if len(cells) >= 6:
                        inmuebles_data["inmueble_imagenes"] = cells[5].text.strip()

            else:
                # Fallback: al menos intentar extraer partida por regex
                partida_match = re.search(r"(P?\d{8,})", page_text)
                if partida_match:
                    inmuebles_data["inmueble_partida_registral"] = partida_match.group(1)

            # Si no se llenó tipo, heurística por texto
            if not inmuebles_data["inmueble_tipo"]:
                tipos_inmuebles = ["CASA", "DEPARTAMENTO", "TERRENO", "LOCAL", "OFICINA", "EDIFICIO"]
                upper = page_text.upper()
                for tipo in tipos_inmuebles:
                    if tipo in upper:
                        inmuebles_data["inmueble_tipo"] = tipo
                        break

        except Exception as e:
            logger.warning(f"⚠️ No se pudo parsear tabla de Inmuebles: {e}")

        logger.info(
            f"✅ Pestaña INMUEBLES: {inmuebles_data['inmueble_tipo']} "
            f"en {inmuebles_data['inmueble_distrito']} "
            f"(Partida {inmuebles_data['inmueble_partida_registral']})"
        )

    except Exception as e:
        logger.error(f"Error en extract_inmuebles_tab_info: {e}")

    return inmuebles_data


# ---------------------------------------------------------
# PESTAÑA CRONOGRAMA
# ---------------------------------------------------------

def _norm_header(text):
    t = text.strip().lower()
    if "fase" in t:
        return "fase"
    if "fecha" in t and "inicio" in t:
        return "fecha_inicio"
    if "fecha" in t and "fin" in t:
        return "fecha_fin"
    if "hora" in t and "inicio" in t:
        return "hora_inicio"
    if "hora" in t and "fin" in t:
        return "hora_fin"
    return t.replace(" ", "_")


def extract_cronograma_tab_info(driver):
    cronograma_data = {
        "cronograma_fases": [],
        "cronograma_texto_completo": "",
    }

    try:
        try:
            tab = driver.find_element(
                By.XPATH,
                "//a[contains(., 'Cronograma') or contains(@href, 'cronograma') "
                "or contains(@onclick, 'cronograma')]",
            )
            driver.execute_script("arguments[0].click();", tab)
            time.sleep(2)
            logger.info("✅ Navegó a pestaña Cronograma")
        except Exception:
            logger.warning("⚠️ No se pudo hacer clic en pestaña Cronograma")

        body = driver.find_element(By.TAG_NAME, "body")
        cronograma_data["cronograma_texto_completo"] = body.text

        # Buscar la tabla de cronograma de manera genérica
        try:
            tables = body.find_elements(By.TAG_NAME, "table")
            target_table = None
            for t in tables:
                rows = t.find_elements(By.XPATH, ".//tr")
                if len(rows) >= 2:
                    cols = rows[0].find_elements(By.XPATH, ".//th|.//td")
                    if len(cols) >= 2:
                        target_table = t
                        break

            if not target_table:
                raise Exception("No se encontró tabla de cronograma con estructura mínima")

            # Encabezados
            header_cells = target_table.find_elements(By.XPATH, ".//thead//th")
            if not header_cells:
                header_cells = target_table.find_elements(
                    By.XPATH, ".//tbody/tr[1]/th | .//tbody/tr[1]/td"
                )

            headers = [_norm_header(h.text) for h in header_cells]

            # Filas
            rows = target_table.find_elements(By.XPATH, ".//tbody/tr")
            fases = []
            for row in rows:
                cells = row.find_elements(By.XPATH, ".//td")
                if not cells:
                    continue
                fase = {}
                for idx, cell in enumerate(cells):
                    key = headers[idx] if idx < len(headers) else f"col_{idx}"
                    fase[key] = cell.text.strip()
                fases.append(fase)

            cronograma_data["cronograma_fases"] = fases
            logger.info(
                f"✅ Pestaña CRONOGRAMA: {len(fases)} filas de cronograma extraídas"
            )

        except Exception as e:
            logger.warning(f"⚠️ No se pudo extraer tabla cronograma estructurada: {e}")

    except Exception as e:
        logger.error(f"Error en extract_cronograma_tab_info: {e}")

    return cronograma_data


# ---------------------------------------------------------
# DETALLE COMPLETO
# ---------------------------------------------------------

def extract_detail_page_info(driver):
    detail_data = {}
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        logger.info("📋 Extrayendo información de pestaña REMATE")
        detail_data.update(extract_remate_tab_info(driver))

        logger.info("🏠 Navegando a pestaña INMUEBLES")
        detail_data.update(extract_inmuebles_tab_info(driver))

        logger.info("📅 Navegando a pestaña CRONOGRAMA")
        detail_data.update(extract_cronograma_tab_info(driver))

        logger.info("✅ Información completa extraída de las 3 pestañas")
    except Exception as e:
        logger.error(f"Error extrayendo información de detalle: {e}")

    return detail_data


# ---------------------------------------------------------
# LISTADO: BÁSICO
# ---------------------------------------------------------

def extract_basic_remate_info_only(driver):
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [l.strip() for l in page_text.split("\n") if l.strip()]
        remates_info = []

        for i, line in enumerate(lines):
            if "remate n" in line.lower() and "convocatoria" in line.lower():
                m = REMATE_REGEX.search(line)
                if not m:
                    logger.debug(
                        f"No se pudo extraer número de remate de línea: {line}"
                    )
                    continue
                numero = m.group(1)
                info = {
                    "numero": numero,
                    "numero_remate": line,
                    "line_index": i,
                    "tipo_convocatoria": (
                        "PRIMERA"
                        if "primera" in line.lower()
                        else "SEGUNDA"
                        if "segunda" in line.lower()
                        else "TERCERA"
                        if "tercera" in line.lower()
                        else ""
                    ),
                    "row_index": len(remates_info),
                }
                remates_info.append(info)
                logger.info(
                    f"📋 Remate {numero} encontrado (row_index={info['row_index']})"
                )

        logger.info(f"📄 Total remates básicos: {len(remates_info)}")
        return remates_info

    except Exception as e:
        logger.error(f"Error en extract_basic_remate_info_only: {e}")
        return []


# ---------------------------------------------------------
# CLICK DETALLE (MISMA PESTAÑA)
# ---------------------------------------------------------

def click_detail_by_row_index(driver, row_index):
    """
    Hacer clic en el botón 'Detalle' correspondiente a la fila dada.
    """
    try:
        logger.info(f"🎯 Buscando botón Detalle para row_index={row_index}")

        # Verificar que estamos en un listado de remates; si no, intentar volver
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            if "remate n" not in body_text and "remate n°" not in body_text:
                logger.info(
                    "🔁 No se detecta texto de listado de remates; intentando volver con back()"
                )
                try:
                    driver.back()
                    time.sleep(3)
                except Exception as be:
                    logger.warning(f"⚠️ Error al hacer back() previo: {be}")
        except Exception:
            pass

        # Esperar a que haya botones Detalle en la página actual
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, DETALLE_XPATH))
            )
        except Exception as e:
            logger.error(
                f"❌ No se encontraron botones Detalle en la página actual: {e}"
            )
            return False

        buttons = driver.find_elements(By.XPATH, DETALLE_XPATH)
        logger.info(f"🔍 Botones Detalle visibles en página: {len(buttons)}")

        if not buttons:
            logger.error("❌ No hay ningún botón Detalle en la página")
            return False

        if row_index >= len(buttons):
            logger.error(
                f"❌ row_index={row_index} fuera de rango (total botones={len(buttons)})"
            )
            return False

        btn = buttons[row_index]
        if not (btn.is_displayed() and btn.is_enabled()):
            logger.error("❌ Botón Detalle no está visible/habilitado")
            return False

        original_url = driver.current_url

        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", btn
        )
        time.sleep(0.5)

        try:
            btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", btn)

        # Esperar navegación (URL distinta o contenido de detalle)
        def _detail_loaded(d):
            if d.current_url != original_url:
                return True
            txt = d.find_element(By.TAG_NAME, "body").text.lower()
            return "expediente" in txt or "tasación" in txt

        WebDriverWait(driver, 10).until(_detail_loaded)

        txt = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "expediente" in txt or "tasación" in txt:
            logger.info(f"✅ Navegación exitosa al detalle (row_index={row_index})")
            return True

        logger.warning(
            "⚠️ Después del clic en Detalle no se detectó contenido típico de detalle"
        )
        return True

    except Exception as e:
        logger.error(f"Error en click_detail_by_row_index({row_index}): {e}")
        return False


# ---------------------------------------------------------
# VOLVER AL LISTADO DESDE DETALLE
# ---------------------------------------------------------

def return_to_list_from_detail(driver):
    """
    Volver desde la página de detalle al listado de remates.
    """
    try:
        back_locators = [
            "//button[contains(.,'Regresar') or contains(.,'Volver') or contains(.,'Atrás')]",
            "//a[contains(.,'Regresar') or contains(.,'Volver') or contains(.,'Atrás')]",
        ]

        clicked = False
        for locator in back_locators:
            try:
                el = driver.find_element(By.XPATH, locator)
                if el.is_displayed() and el.is_enabled():
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", el
                    )
                    time.sleep(0.5)
                    try:
                        el.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", el)
                    time.sleep(3)
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            logger.info("🔁 No se encontró botón 'Regresar'; usando driver.back()")
            driver.back()
            time.sleep(3)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, DETALLE_XPATH))
            )
        except Exception as e:
            logger.warning(
                f"⚠️ Tras volver al listado no se encontraron botones Detalle: {e}"
            )

    except Exception as e:
        logger.warning(f"⚠️ Error en return_to_list_from_detail: {e}")


# ---------------------------------------------------------
# PAGINACIÓN
# ---------------------------------------------------------

def navigate_to_next_page(driver, target_page):
    """
    Navegación a la página indicada, soportando paginador clásico y
    paginador PrimeFaces (ui-paginator-page / ui-paginator-next).
    """
    try:
        logger.info(f"🔄 Navegando a página {target_page}")
        time.sleep(1)

        # 1) Intentar enlaces numéricos normales
        try:
            link = driver.find_element(
                By.XPATH, f"//a[normalize-space(text())='{target_page}']"
            )
            if link.is_displayed():
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", link
                )
                time.sleep(0.5)
                try:
                    link.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", link)
                time.sleep(3)
                return True
        except Exception as e:
            logger.debug(
                f"No se encontró enlace <a> directo a página {target_page}: {e}"
            )

        # 2) Intentar paginador PrimeFaces (ui-paginator-page)
        try:
            pages = driver.find_elements(
                By.CSS_SELECTOR, "a.ui-paginator-page"
            )
            for p in pages:
                if p.text.strip() == str(target_page):
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", p
                    )
                    time.sleep(0.5)
                    try:
                        p.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", p)
                    time.sleep(3)
                    return True
        except Exception as e:
            logger.debug(
                f"No se pudo navegar por ui-paginator-page a {target_page}: {e}"
            )

        # 3) Fallback: botón "Siguiente"
        try:
            next_selectors = [
                "//a[normalize-space(text())='»' or normalize-space(text())='>' "
                "or contains(normalize-space(text()), 'Siguiente') "
                "or contains(normalize-space(text()), 'Next')]",
                "//span[contains(@class,'ui-paginator-next')]",
            ]
            for sel in next_selectors:
                try:
                    nb = driver.find_element(By.XPATH, sel)
                    if nb.is_displayed() and nb.is_enabled():
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});", nb
                        )
                        time.sleep(0.5)
                        try:
                            nb.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", nb)
                        time.sleep(3)
                        return True
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Error con botón siguiente: {e}")

        logger.error(f"❌ No se pudo navegar a página {target_page}")
        return False

    except Exception as e:
        logger.error(f"Error en navigate_to_next_page: {e}")
        return False


# ---------------------------------------------------------
# FUNCIÓN PRINCIPAL
# ---------------------------------------------------------

def scrape_all_pages_with_details():
    driver = None
    url = "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml"

    try:
        logger.info("🚀 Iniciando scraping REMAJU - TODAS LAS PÁGINAS CON DETALLES")

        driver = setup_driver()
        driver.set_page_load_timeout(30)

        logger.info(f"Navegando a: {url}")
        driver.get(url)
        # tiempo para captcha + filtros si los haces a mano
        time.sleep(8)

        all_remates = []
        current_page = 1
        max_pages = 25          # Límite explícito a 25 páginas
        failed_pages = 0
        max_failed = 3

        while current_page <= max_pages and failed_pages < max_failed:
            logger.info(
                f"\n📄 PROCESANDO PÁGINA {current_page} "
                f"(Total remates acumulados: {len(all_remates)})"
            )

            try:
                remates_info = extract_basic_remate_info_only(driver)

                if remates_info:
                    failed_pages = 0

                    for i, remate_info in enumerate(remates_info):
                        n = remate_info["numero"]
                        row_index = remate_info.get("row_index", i)

                        logger.info(
                            f"  📋 REMATE {i+1}/{len(remates_info)} - Número "
                            f"{n} (row_index={row_index})"
                        )

                        try:
                            if click_detail_by_row_index(driver, row_index):
                                detail = extract_detail_page_info(driver)

                                complete = {
                                    **remate_info,
                                    **detail,
                                    "procesado_detalle": True,
                                    "pagina": current_page,
                                    "index_global": len(all_remates) + 1,
                                    "timestamp_detalle": datetime.now().isoformat(),
                                }
                                all_remates.append(complete)
                                logger.info(
                                    f"  ✅ Remate {n} procesado completamente"
                                )
                            else:
                                all_remates.append(
                                    {
                                        **remate_info,
                                        "procesado_detalle": False,
                                        "error_detalle": "No se pudo acceder a detalle",
                                        "pagina": current_page,
                                        "index_global": len(all_remates) + 1,
                                    }
                                )
                                logger.warning(
                                    f"  ⚠️ Remate {n} sin detalles"
                                )

                        except Exception as e:
                            logger.error(
                                f"  ❌ Error procesando remate {n}: {e}"
                            )
                            all_remates.append(
                                {
                                    **remate_info,
                                    "procesado_detalle": False,
                                    "error_detalle": str(e),
                                    "pagina": current_page,
                                    "index_global": len(all_remates) + 1,
                                }
                            )

                        # Volver al listado SIEMPRE usando la función auxiliar
                        try:
                            return_to_list_from_detail(driver)
                        except Exception as e:
                            logger.warning(
                                f"⚠️ Problema al volver al listado tras remate {n}: {e}"
                            )

                    logger.info(
                        f"✅ PÁGINA {current_page}: {len(remates_info)} remates procesados"
                    )

                else:
                    logger.warning(f"⚠️ Página {current_page}: Sin remates encontrados")
                    failed_pages += 1

                # Si ya llegamos a max_pages, no intentes navegar más
                if current_page >= max_pages:
                    logger.info(f"🛑 Límite de páginas alcanzado: {max_pages}")
                    break

                if navigate_to_next_page(driver, current_page + 1):
                    current_page += 1
                else:
                    logger.error(
                        f"❌ No se pudo navegar a página {current_page + 1}"
                    )
                    failed_pages += 1
                    break

            except Exception as e:
                logger.error(f"❌ Error en página {current_page}: {e}")
                failed_pages += 1
                break

        remates_con_detalle = len(
            [r for r in all_remates if r.get("procesado_detalle", False)]
        )
        remates_con_precio = len(
            [r for r in all_remates if r.get("precio_base_numerico", 0) > 0]
        )

        resultado = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "url": url,
            "scraping_mode": "complete_all_pages_with_details",
            "resumen": {
                "total_remates": len(all_remates),
                "remates_con_detalle": remates_con_detalle,
                "remates_con_precio": remates_con_precio,
                "paginas_procesadas": current_page - 1,
                "completitud_detalle_pct": round(
                    (remates_con_detalle / len(all_remates) * 100)
                    if all_remates
                    else 0,
                    1,
                ),
                "completitud_precio_pct": round(
                    (remates_con_precio / len(all_remates) * 100)
                    if all_remates
                    else 0,
                    1,
                ),
            },
            "remates": all_remates,
        }

        with open("remates_result_fixed.json", "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)

        logger.info("🎯 SCRAPING COMPLETADO:")
        logger.info(f"   📊 TOTAL REMATES: {len(all_remates)}")
        logger.info(f"   📄 PÁGINAS: {current_page - 1}")
        logger.info(f"   ✅ CON DETALLE: {remates_con_detalle}")
        logger.info(f"   💰 CON PRECIO: {remates_con_precio}")

        print(f"total_remates={len(all_remates)}")
        print(f"remates_con_detalle={remates_con_detalle}")
        print(f"total_pages={current_page - 1}")
        print("status=success")

        return resultado

    except Exception as e:
        logger.error(f"❌ Error general: {e}")
        print("status=error")
        return {"status": "error", "error": str(e)}

    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    result = scrape_all_pages_with_details()
    print("=" * 60)
    print(f"RESULTADO FINAL: {result.get('status')}")
    if "resumen" in result:
        print(f"🎯 TOTAL REMATES: {result['resumen']['total_remates']}")
        print(f"📄 PÁGINAS: {result['resumen']['paginas_procesadas']}")
        print(f"✅ CON DETALLE: {result['resumen']['remates_con_detalle']}")
        print(f"💰 CON PRECIO: {result['resumen']['remates_con_precio']}")
        print(
            f"📈 COMPLETITUD: {result['resumen']['completitud_detalle_pct']}%"
        )
