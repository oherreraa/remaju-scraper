import json
import os
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
# CONFIGURACIÓN BÁSICA
# ---------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REMATE_REGEX = re.compile(r"remate\s+n[°º]?\s*(\d+)", re.IGNORECASE)

DETALLE_XPATH = (
    "//a[normalize-space(.)='Detalle']"
    " | //input[@value='Detalle']"
    " | //button[normalize-space(.)='Detalle']"
)


# ---------------------------------------------------------
# SETUP DRIVER
# ---------------------------------------------------------

def setup_driver():
    """Configurar Chrome driver optimizado."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1366,768")

    # (algunas flags serán ignoradas, no pasa nada)
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-web-security")

    # Anti-detección básico
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
# EXTRACCIÓN: PESTAÑA REMATE
# ---------------------------------------------------------

def extract_remate_tab_info(driver):
    """Extraer información de la pestaña REMATE."""
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
        lines = [line.strip() for line in page_text.split("\n") if line.strip()]

        for i, line in enumerate(lines):
            if line.startswith("Expediente") and i + 1 < len(lines):
                remate_data["expediente"] = lines[i + 1]
            elif line.startswith("Distrito Judicial") and i + 1 < len(lines):
                remate_data["distrito_judicial"] = lines[i + 1]
            elif line.startswith("Órgano Jurisdiccional") and i + 1 < len(lines):
                remate_data["organo_jurisdiccional"] = lines[i + 1]
            elif line.startswith("Instancia") and i + 1 < len(lines):
                remate_data["instancia"] = lines[i + 1]
            elif line.startswith("Juez") and i + 1 < len(lines):
                remate_data["juez"] = lines[i + 1]
            elif line.startswith("Especialista") and i + 1 < len(lines):
                remate_data["especialista"] = lines[i + 1]
            elif line.startswith("Materia") and i + 1 < len(lines):
                remate_data["materia"] = lines[i + 1]
            elif line.startswith("Resolución") and i + 1 < len(lines):
                remate_data["resolucion"] = lines[i + 1]
            elif line.startswith("Fecha Resolución") and i + 1 < len(lines):
                remate_data["fecha_resolucion"] = lines[i + 1]
            elif line.startswith("Archivo") and i + 1 < len(lines):
                remate_data["archivo_resolucion"] = lines[i + 1]
            elif line.startswith("Convocatoria") and i + 1 < len(lines):
                remate_data["convocatoria"] = lines[i + 1]
            elif line.startswith("Tipo Cambio") and i + 1 < len(lines):
                remate_data["tipo_cambio"] = lines[i + 1]
            elif line.startswith("Tasación") and i + 1 < len(lines):
                remate_data["tasacion"] = lines[i + 1]
            elif line.startswith("Precio Base") and i + 1 < len(lines):
                precio_base = lines[i + 1]
                remate_data["precio_base"] = precio_base

                text_clean = precio_base.replace(",", "")
                numbers = re.findall(r"\d+\.?\d*", text_clean)

                if "$" in precio_base:
                    remate_data["precio_base_moneda"] = "USD"
                elif "S/" in precio_base or "S/." in precio_base:
                    remate_data["precio_base_moneda"] = "PEN"

                if numbers:
                    try:
                        remate_data["precio_base_numerico"] = float(numbers[0])
                    except Exception:
                        pass

            elif line.startswith("Incremento entre ofertas") and i + 1 < len(lines):
                remate_data["incremento_ofertas"] = lines[i + 1]
            elif line.startswith("Arancel") and i + 1 < len(lines):
                remate_data["arancel"] = lines[i + 1]
            elif line.startswith("Oblaje") and i + 1 < len(lines):
                remate_data["oblaje"] = lines[i + 1]
            elif line.startswith("Descripción") and i + 1 < len(lines):
                remate_data["descripcion_completa"] = lines[i + 1]
            elif line.startswith("N° inscritos") and i + 1 < len(lines):
                remate_data["num_inscritos"] = lines[i + 1]

        logger.info(
            f"✅ Pestaña REMATE: Expediente {remate_data['expediente']}, "
            f"Precio {remate_data['precio_base']}"
        )

    except Exception as e:
        logger.error(f"Error en extract_remate_tab_info: {e}")

    return remate_data


# ---------------------------------------------------------
# EXTRACCIÓN: PESTAÑA INMUEBLES
# ---------------------------------------------------------

def extract_inmuebles_tab_info(driver):
    """Extraer información de la pestaña INMUEBLES."""
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
        try:
            inmuebles_tab = driver.find_element(
                By.XPATH,
                (
                    "//a[contains(., 'Inmuebles') or contains(@href, 'inmuebles') "
                    "or contains(@onclick, 'inmuebles')]"
                ),
            )
            driver.execute_script("arguments[0].click();", inmuebles_tab)
            time.sleep(2)
            logger.info("✅ Navegó a pestaña Inmuebles")
        except Exception:
            logger.warning("⚠️ No se pudo hacer clic en pestaña Inmuebles")

        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in page_text.split("\n") if line.strip()]

        for i, line in enumerate(lines):
            if line.startswith("Distrito Judicial") and i + 1 < len(lines):
                inmuebles_data["inmueble_distrito_judicial"] = lines[i + 1]
            elif line.startswith("Departamento") and i + 1 < len(lines):
                inmuebles_data["inmueble_departamento"] = lines[i + 1]
            elif line.startswith("Provincia") and i + 1 < len(lines):
                inmuebles_data["inmueble_provincia"] = lines[i + 1]
            elif line.startswith("Distrito") and i + 1 < len(lines):
                inmuebles_data["inmueble_distrito"] = lines[i + 1]

        table_text = page_text

        partida_match = re.search(r"(P?\d{8,})", table_text)
        if partida_match:
            inmuebles_data["inmueble_partida_registral"] = partida_match.group(1)

        tipos_inmuebles = [
            "CASA",
            "DEPARTAMENTO",
            "TERRENO",
            "LOCAL",
            "OFICINA",
            "EDIFICIO",
        ]
        upper_text = table_text.upper()
        for tipo in tipos_inmuebles:
            if tipo in upper_text:
                inmuebles_data["inmueble_tipo"] = tipo
                break

        logger.info(
            f"✅ Pestaña INMUEBLES: {inmuebles_data['inmueble_tipo']} "
            f"en {inmuebles_data['inmueble_distrito']}"
        )

    except Exception as e:
        logger.error(f"Error en extract_inmuebles_tab_info: {e}")

    return inmuebles_data


# ---------------------------------------------------------
# EXTRACCIÓN: PESTAÑA CRONOGRAMA
# ---------------------------------------------------------

def _normalize_cronograma_header(text):
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
    """Extraer información de la pestaña CRONOGRAMA (tabla estructurada)."""
    cronograma_data = {
        "cronograma_fases": [],
        "cronograma_texto_completo": "",
    }

    try:
        try:
            cronograma_tab = driver.find_element(
                By.XPATH,
                (
                    "//a[contains(., 'Cronograma') or contains(@href, 'cronograma') "
                    "or contains(@onclick, 'cronograma')]"
                ),
            )
            driver.execute_script("arguments[0].click();", cronograma_tab)
            time.sleep(2)
            logger.info("✅ Navegó a pestaña Cronograma")
        except Exception:
            logger.warning("⚠️ No se pudo hacer clic en pestaña Cronograma")

        page_text = driver.find_element(By.TAG_NAME, "body").text
        cronograma_data["cronograma_texto_completo"] = page_text

        # Intentar localizar tabla de cronograma
        try:
            table = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//table[contains(@class,'ui-datatable') or "
                        "contains(@id,'ronograma')]",
                    )
                )
            )

            headers_raw = table.find_elements(By.XPATH, ".//thead//th")
            headers = [_normalize_cronograma_header(h.text) for h in headers_raw]

            rows = table.find_elements(By.XPATH, ".//tbody/tr")
            fases = []

            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
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
            logger.warning(
                f"⚠️ No se pudo extraer tabla cronograma estructurada: {e}"
            )

    except Exception as e:
        logger.error(f"Error en extract_cronograma_tab_info: {e}")

    return cronograma_data


# ---------------------------------------------------------
# EXTRACCIÓN COMPLETA DE PÁGINA DE DETALLE
# ---------------------------------------------------------

def extract_detail_page_info(driver):
    """Extraer toda la información de la página de detalle."""
    detail_data = {}

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        logger.info("📋 Extrayendo información de pestaña REMATE")
        remate_info = extract_remate_tab_info(driver)
        detail_data.update(remate_info)

        logger.info("🏠 Navegando a pestaña INMUEBLES")
        inmuebles_info = extract_inmuebles_tab_info(driver)
        detail_data.update(inmuebles_info)

        logger.info("📅 Navegando a pestaña CRONOGRAMA")
        cronograma_info = extract_cronograma_tab_info(driver)
        detail_data.update(cronograma_info)

        logger.info("✅ Información completa extraída de las 3 pestañas")
        return detail_data

    except Exception as e:
        logger.error(f"Error extrayendo información de detalle: {e}")
        return detail_data


# ---------------------------------------------------------
# LISTADO: EXTRACCIÓN BÁSICA POR PÁGINA
# ---------------------------------------------------------

def extract_basic_remate_info_only(driver):
    """
    Extraer solo información básica de remates en la página actual.

    Se asume que el orden de aparición de los títulos 'Remate N° ...'
    coincide con el orden de los botones 'Detalle' en los cards.
    """
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in page_text.split("\n") if line.strip()]
        remates_info = []

        for i, line in enumerate(lines):
            if "remate n" in line.lower() and "convocatoria" in line.lower():
                numero_match = REMATE_REGEX.search(line)
                if not numero_match:
                    logger.debug(
                        f"No se pudo extraer número de remate de línea: {line}"
                    )
                    continue

                remate_numero = numero_match.group(1)

                remate_info = {
                    "numero": remate_numero,
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
                    "row_index": len(remates_info),  # 0-based
                }

                remates_info.append(remate_info)
                logger.info(
                    f"📋 Remate {remate_numero} encontrado "
                    f"(row_index={remate_info['row_index']})"
                )

        logger.info(f"📄 Total remates básicos: {len(remates_info)}")
        return remates_info

    except Exception as e:
        logger.error(f"Error en extract_basic_remate_info_only: {e}")
        return []


# ---------------------------------------------------------
# NAVEGACIÓN DETALLE <-> LISTADO
# ---------------------------------------------------------

def click_detail_by_row_index(driver, row_index, list_window_handle):
    """
    Hacer clic en el botón 'Detalle' correspondiente a la fila dada.

    Maneja tanto el caso de navegación en la misma pestaña como
    el caso en que se abre una nueva pestaña/ventana.
    """
    try:
        logger.info(f"🎯 Buscando botón Detalle para row_index={row_index}")

        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, DETALLE_XPATH))
        )
        detail_buttons = driver.find_elements(By.XPATH, DETALLE_XPATH)
        logger.info(f"🔍 Botones Detalle encontrados: {len(detail_buttons)}")

        if row_index >= len(detail_buttons):
            logger.error(
                f"❌ row_index={row_index} fuera de rango "
                f"(total botones={len(detail_buttons)})"
            )
            return False

        button = detail_buttons[row_index]

        if not (button.is_displayed() and button.is_enabled()):
            logger.error(
                f"❌ Botón Detalle en row_index={row_index} no está clicable"
            )
            return False

        original_url = driver.current_url
        original_handles = driver.window_handles.copy()

        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", button
        )
        time.sleep(0.5)

        try:
            button.click()
        except Exception:
            driver.execute_script("arguments[0].click();", button)

        def _detail_loaded(d):
            # ¿nueva pestaña?
            handles = d.window_handles
            if len(handles) > len(original_handles):
                new_handle = [h for h in handles if h not in original_handles][0]
                d.switch_to.window(new_handle)
                return True
            # ¿misma pestaña con URL distinta?
            if d.current_url != original_url:
                return True
            return False

        WebDriverWait(driver, 10).until(_detail_loaded)

        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "expediente" in page_text or "tasación" in page_text:
            logger.info(f"✅ Navegación exitosa al detalle (row_index={row_index})")
            return True

        logger.warning(
            "⚠️ Navegó tras clic en Detalle pero no se detectó texto típico de detalle"
        )
        return True

    except Exception as e:
        logger.error(f"Error en click_detail_by_row_index({row_index}): {e}")
        # Asegurar volver al window del listado si algo salió muy mal
        try:
            if driver.current_window_handle != list_window_handle:
                driver.close()
                driver.switch_to.window(list_window_handle)
        except Exception:
            pass
        return False


def safe_return_to_list(driver, list_window_handle):
    """
    Volver desde la página de detalle al listado original
    sin lanzar excepciones hacia arriba.
    """
    try:
        if driver.current_window_handle != list_window_handle:
            # Detalle en nueva pestaña/ventana
            driver.close()
            driver.switch_to.window(list_window_handle)
        else:
            # Detalle en la misma pestaña
            driver.back()

        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, DETALLE_XPATH))
        )
        time.sleep(1)
    except Exception as e:
        logger.warning(f"⚠️ Problema al volver al listado: {e}")


# ---------------------------------------------------------
# PAGINACIÓN
# ---------------------------------------------------------

def navigate_to_next_page(driver, target_page):
    """Navegación a página específica o uso de botón Siguiente."""
    try:
        logger.info(f"🔄 Navegando a página {target_page}")
        time.sleep(1)

        # Intentar por enlace con texto exacto
        try:
            page_link = driver.find_element(
                By.XPATH, f"//a[normalize-space(text())='{target_page}']"
            )
            if page_link.is_displayed():
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", page_link
                )
                time.sleep(0.5)
                try:
                    page_link.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", page_link)
                time.sleep(3)
                return True
        except Exception as e:
            logger.debug(
                f"No se encontró enlace directo a página {target_page}: {e}"
            )

        # Fallback: botón "Siguiente"
        try:
            next_selectors = [
                "//a[normalize-space(text())='»' or normalize-space(text())='>' "
                "or contains(normalize-space(text()), 'Siguiente') "
                "or contains(normalize-space(text()), 'Next')]",
                "//input[@value='»' or @value='>' or @value='Next']",
                "//button[normalize-space(text())='»' or normalize-space(text())='>' "
                "or contains(normalize-space(text()), 'Siguiente') "
                "or contains(normalize-space(text()), 'Next')]",
            ]
            for selector in next_selectors:
                try:
                    next_button = driver.find_element(By.XPATH, selector)
                    if next_button.is_displayed() and next_button.is_enabled():
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});",
                            next_button,
                        )
                        time.sleep(0.5)
                        try:
                            next_button.click()
                        except Exception:
                            driver.execute_script(
                                "arguments[0].click();", next_button
                            )
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
    """Función principal para scrapear todas las páginas con detalles."""
    driver = None
    url = "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml"

    try:
        logger.info("🚀 Iniciando scraping REMAJU - TODAS LAS PÁGINAS CON DETALLES")

        driver = setup_driver()
        driver.set_page_load_timeout(30)

        logger.info(f"Navegando a: {url}")
        driver.get(url)
        # Aquí normalmente resuelves el CAPTCHA a mano si existe
        time.sleep(8)

        all_remates = []
        current_page = 1
        max_pages = 100
        failed_pages = 0
        max_failed = 3

        list_window_handle = driver.current_window_handle

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
                        remate_numero = remate_info["numero"]
                        row_index = remate_info.get("row_index", i)

                        logger.info(
                            f"  📋 REMATE {i+1}/{len(remates_info)} - Número "
                            f"{remate_numero} (row_index={row_index})"
                        )

                        remate_result = None

                        try:
                            clicked = click_detail_by_row_index(
                                driver, row_index, list_window_handle
                            )

                            if clicked:
                                detailed_info = extract_detail_page_info(driver)

                                remate_result = {
                                    **remate_info,
                                    **detailed_info,
                                    "procesado_detalle": True,
                                    "pagina": current_page,
                                    "index_global": len(all_remates) + 1,
                                    "timestamp_detalle": datetime.now().isoformat(),
                                }
                                logger.info(
                                    f"  ✅ Remate {remate_numero} procesado completamente"
                                )

                                # Volver al listado desde detalle
                                safe_return_to_list(driver, list_window_handle)
                            else:
                                remate_result = {
                                    **remate_info,
                                    "procesado_detalle": False,
                                    "error_detalle": "No se pudo acceder a detalle",
                                    "pagina": current_page,
                                    "index_global": len(all_remates) + 1,
                                }
                                logger.warning(
                                    f"  ⚠️ Remate {remate_numero} sin detalles"
                                )

                        except Exception as e:
                            logger.error(
                                f"  ❌ Error procesando remate {remate_numero}: {e}"
                            )
                            remate_result = {
                                **remate_info,
                                "procesado_detalle": False,
                                "error_detalle": str(e),
                                "pagina": current_page,
                                "index_global": len(all_remates) + 1,
                            }
                            # Intentar recuperar contexto al listado
                            safe_return_to_list(driver, list_window_handle)

                        all_remates.append(remate_result)
                        time.sleep(0.5)

                    logger.info(
                        f"✅ PÁGINA {current_page}: {len(remates_info)} remates procesados"
                    )

                else:
                    logger.warning(f"⚠️ Página {current_page}: Sin remates encontrados")
                    failed_pages += 1

                if navigate_to_next_page(driver, current_page + 1):
                    current_page += 1
                    list_window_handle = driver.current_window_handle
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

        output_file = "remates_result_fixed.json"
        with open(output_file, "w", encoding="utf-8") as f:
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


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

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
