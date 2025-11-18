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
# PESTAÑA REMATE
# ---------------------------------------------------------

def extract_remate_tab_info(driver):
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
                precio = lines[i + 1]
                remate_data["precio_base"] = precio

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
# PESTAÑA INMUEBLES
# ---------------------------------------------------------

def extract_inmuebles_tab_info(driver):
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
            tab = driver.find_element(
                By.XPATH,
                "//a[contains(., 'Inmuebles') or contains(@href, 'inmuebles') "
                "or contains(@onclick, 'inmuebles')]",
            )
            driver.execute_script("arguments[0].click();", tab)
            time.sleep(2)
            logger.info("✅ Navegó a pestaña Inmuebles")
        except Exception:
            logger.warning("⚠️ No se pudo hacer clic en pestaña Inmuebles")

        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [l.strip() for l in page_text.split("\n") if l.strip()]

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

        tipos = ["CASA", "DEPARTAMENTO", "TERRENO", "LOCAL", "OFICINA", "EDIFICIO"]
        upper = table_text.upper()
        for t in tipos:
            if t in upper:
                inmuebles_data["inmueble_tipo"] = t
                break

        logger.info(
            f"✅ Pestaña INMUEBLES: {inmuebles_data['inmueble_tipo']} "
            f"en {inmuebles_data['inmueble_distrito']}"
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
                # usar primera fila como encabezado
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
    try:
        logger.info(f"🎯 Buscando botón Detalle para row_index={row_index}")

        # Esperar a que haya algún Detalle en la página
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, DETALLE_XPATH))
        )
        buttons = driver.find_elements(By.XPATH, DETALLE_XPATH)
        logger.info(f"🔍 Botones Detalle encontrados: {len(buttons)}")

        if row_index >= len(buttons):
            logger.error(
                f"❌ row_index={row_index} fuera de rango (total botones={len(buttons)})"
            )
            return False

        btn = buttons[row_index]
        if not (btn.is_displayed() and btn.is_enabled()):
            logger.error("❌ Botón Detalle no clicable")
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

        # Esperar navegación a detalle (misma pestaña)
        WebDriverWait(driver, 10).until(
            lambda d: d.current_url != original_url
        )

        txt = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "expediente" in txt or "tasación" in txt:
            logger.info(f"✅ Navegación exitosa al detalle (row_index={row_index})")
            return True

        logger.warning(
            "⚠️ Navegó tras clic en Detalle pero no se detectó texto típico de detalle"
        )
        return True

    except Exception as e:
        logger.error(f"Error en click_detail_by_row_index({row_index}): {e}")
        return False


# ---------------------------------------------------------
# PAGINACIÓN
# ---------------------------------------------------------

def navigate_to_next_page(driver, target_page):
    try:
        logger.info(f"🔄 Navegando a página {target_page}")
        time.sleep(1)

        # intentar enlace numérico
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
            logger.debug(f"No se encontró enlace directo a página {target_page}: {e}")

        # fallback siguiente
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
        max_pages = 100
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

                        # volver al listado con back siempre
                        try:
                            driver.back()
                            time.sleep(3)
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
