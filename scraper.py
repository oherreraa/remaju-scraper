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

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_driver():
    """Configurar Chrome driver optimizado"""
    chrome_options = Options()
    
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1366,768')
    
    # Optimizaciones de velocidad
    chrome_options.add_argument('--disable-images')
    chrome_options.add_argument('--disable-plugins')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-web-security')
    
    # Anti-detección básico
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36')
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def extract_remate_tab_info(driver):
    """Extraer información de la pestaña REMATE"""
    remate_data = {
        "expediente": "", "distrito_judicial": "", "organo_jurisdiccional": "",
        "instancia": "", "juez": "", "especialista": "", "materia": "",
        "resolucion": "", "fecha_resolucion": "", "archivo_resolucion": "",
        "convocatoria": "", "tipo_cambio": "", "tasacion": "",
        "precio_base": "", "precio_base_numerico": 0, "precio_base_moneda": "",
        "incremento_ofertas": "", "arancel": "", "oblaje": "",
        "descripcion_completa": "", "num_inscritos": ""
    }
    
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        
        for i, line in enumerate(lines):
            if line == "Expediente" and i + 1 < len(lines):
                remate_data["expediente"] = lines[i + 1]
            elif line == "Distrito Judicial" and i + 1 < len(lines):
                remate_data["distrito_judicial"] = lines[i + 1]
            elif line == "Órgano Jurisdiccional" and i + 1 < len(lines):
                remate_data["organo_jurisdiccional"] = lines[i + 1]
            elif line == "Instancia" and i + 1 < len(lines):
                remate_data["instancia"] = lines[i + 1]
            elif line == "Juez" and i + 1 < len(lines):
                remate_data["juez"] = lines[i + 1]
            elif line == "Especialista" and i + 1 < len(lines):
                remate_data["especialista"] = lines[i + 1]
            elif line == "Materia" and i + 1 < len(lines):
                remate_data["materia"] = lines[i + 1]
            elif line == "Resolución" and i + 1 < len(lines):
                remate_data["resolucion"] = lines[i + 1]
            elif line == "Fecha Resolución" and i + 1 < len(lines):
                remate_data["fecha_resolucion"] = lines[i + 1]
            elif line == "Archivo" and i + 1 < len(lines):
                remate_data["archivo_resolucion"] = lines[i + 1]
            elif line == "Convocatoria" and i + 1 < len(lines):
                remate_data["convocatoria"] = lines[i + 1]
            elif line == "Tipo Cambio" and i + 1 < len(lines):
                remate_data["tipo_cambio"] = lines[i + 1]
            elif line == "Tasación" and i + 1 < len(lines):
                remate_data["tasacion"] = lines[i + 1]
            elif line == "Precio Base" and i + 1 < len(lines):
                precio_base = lines[i + 1]
                remate_data["precio_base"] = precio_base
                
                if "$" in precio_base:
                    remate_data["precio_base_moneda"] = "USD"
                    numbers = re.findall(r'[\d,]+\.?\d*', precio_base.replace(',', ''))
                    if numbers:
                        try:
                            remate_data["precio_base_numerico"] = float(numbers[0])
                        except:
                            pass
                elif "S/" in precio_base:
                    remate_data["precio_base_moneda"] = "PEN"
                    numbers = re.findall(r'[\d,]+\.?\d*', precio_base.replace(',', ''))
                    if numbers:
                        try:
                            remate_data["precio_base_numerico"] = float(numbers[0])
                        except:
                            pass
            elif line == "Incremento entre ofertas" and i + 1 < len(lines):
                remate_data["incremento_ofertas"] = lines[i + 1]
            elif line == "Arancel" and i + 1 < len(lines):
                remate_data["arancel"] = lines[i + 1]
            elif line == "Oblaje" and i + 1 < len(lines):
                remate_data["oblaje"] = lines[i + 1]
            elif line == "Descripción" and i + 1 < len(lines):
                remate_data["descripcion_completa"] = lines[i + 1]
            elif line == "N° inscritos" and i + 1 < len(lines):
                remate_data["num_inscritos"] = lines[i + 1]
        
        logger.info(f"✅ Pestaña REMATE: Expediente {remate_data['expediente']}, Precio {remate_data['precio_base']}")
        
    except Exception as e:
        logger.error(f"Error en extract_remate_tab_info: {e}")
    
    return remate_data

def extract_inmuebles_tab_info(driver):
    """Extraer información de la pestaña INMUEBLES"""
    inmuebles_data = {
        "inmueble_distrito_judicial": "", "inmueble_departamento": "",
        "inmueble_provincia": "", "inmueble_distrito": "",
        "inmueble_partida_registral": "", "inmueble_tipo": "",
        "inmueble_direccion": "", "inmueble_cargas_gravamenes": "",
        "inmueble_porcentaje_rematar": "", "inmueble_imagenes": ""
    }
    
    try:
        try:
            inmuebles_tab = driver.find_element(By.XPATH, "//a[contains(text(), 'Inmuebles') or contains(@href, 'inmuebles') or contains(@onclick, 'inmuebles')]")
            driver.execute_script("arguments[0].click();", inmuebles_tab)
            time.sleep(3)
            logger.info("✅ Navegó a pestaña Inmuebles")
        except:
            logger.warning("⚠️ No se pudo hacer clic en pestaña Inmuebles")
        
        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        
        for i, line in enumerate(lines):
            if line == "Distrito Judicial" and i + 1 < len(lines):
                inmuebles_data["inmueble_distrito_judicial"] = lines[i + 1]
            elif line == "Departamento" and i + 1 < len(lines):
                inmuebles_data["inmueble_departamento"] = lines[i + 1]
            elif line == "Provincia" and i + 1 < len(lines):
                inmuebles_data["inmueble_provincia"] = lines[i + 1]
            elif line == "Distrito" and i + 1 < len(lines):
                inmuebles_data["inmueble_distrito"] = lines[i + 1]
        
        table_text = driver.find_element(By.TAG_NAME, "body").text
        
        partida_match = re.search(r'(P?\d{8,})', table_text)
        if partida_match:
            inmuebles_data["inmueble_partida_registral"] = partida_match.group(1)
        
        tipos_inmuebles = ['CASA', 'DEPARTAMENTO', 'TERRENO', 'LOCAL', 'OFICINA', 'EDIFICIO']
        for tipo in tipos_inmuebles:
            if tipo in table_text.upper():
                inmuebles_data["inmueble_tipo"] = tipo
                break
        
        logger.info(f"✅ Pestaña INMUEBLES: {inmuebles_data['inmueble_tipo']} en {inmuebles_data['inmueble_distrito']}")
        
    except Exception as e:
        logger.error(f"Error en extract_inmuebles_tab_info: {e}")
    
    return inmuebles_data

def extract_cronograma_tab_info(driver):
    """Extraer información de la pestaña CRONOGRAMA"""
    cronograma_data = {
        "cronograma_fases": [],
        "cronograma_texto_completo": ""
    }
    
    try:
        try:
            cronograma_tab = driver.find_element(By.XPATH, "//a[contains(text(), 'Cronograma') or contains(@href, 'cronograma') or contains(@onclick, 'cronograma')]")
            driver.execute_script("arguments[0].click();", cronograma_tab)
            time.sleep(3)
            logger.info("✅ Navegó a pestaña Cronograma")
        except:
            logger.warning("⚠️ No se pudo hacer clic en pestaña Cronograma")
        
        page_text = driver.find_element(By.TAG_NAME, "body").text
        cronograma_data["cronograma_texto_completo"] = page_text
        
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        fases = []
        
        for line in lines:
            if re.match(r'^\d+[A-Za-z]', line):
                fase = {"linea_completa": line}
                
                numero_match = re.match(r'^(\d+)', line)
                if numero_match:
                    fase["numero"] = numero_match.group(1)
                
                partes = line.split()
                if len(partes) > 1:
                    fase["fase_nombre"] = partes[1]
                
                fechas = re.findall(r'\d{2}/\d{2}/\d{4}', line)
                if len(fechas) >= 2:
                    fase["fecha_inicio"] = fechas[0]
                    fase["fecha_fin"] = fechas[1]
                
                fases.append(fase)
        
        cronograma_data["cronograma_fases"] = fases
        logger.info(f"✅ Pestaña CRONOGRAMA: {len(fases)} fases extraídas")
        
    except Exception as e:
        logger.error(f"Error en extract_cronograma_tab_info: {e}")
    
    return cronograma_data

def extract_detail_page_info(driver):
    """Extraer toda la información de la página de detalle"""
    detail_data = {}
    
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
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

def extract_basic_remate_info_only(driver):
    """Extraer solo información básica de remates"""
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        remates_info = []
        
        for i, line in enumerate(lines):
            if "remate n°" in line.lower() and "convocatoria" in line.lower():
                numero_match = re.search(r'remate n°?\s*(\d+)', line.lower())
                if numero_match:
                    remate_numero = numero_match.group(1)
                    
                    remate_info = {
                        "numero": remate_numero,
                        "numero_remate": line,
                        "line_index": i,
                        "tipo_convocatoria": "PRIMERA" if "primera" in line.lower() else 
                                           "SEGUNDA" if "segunda" in line.lower() else 
                                           "TERCERA" if "tercera" in line.lower() else ""
                    }
                    
                    remates_info.append(remate_info)
                    logger.info(f"📋 Remate {remate_numero} encontrado")
        
        logger.info(f"📄 Total remates básicos: {len(remates_info)}")
        return remates_info
        
    except Exception as e:
        logger.error(f"Error en extract_basic_remate_info_only: {e}")
        return []

def find_and_click_detail_button_simple(driver, remate_numero):
    """Versión simplificada para encontrar y hacer clic en botón detalle"""
    try:
        logger.info(f"🎯 Buscando detalle para remate {remate_numero}")
        
        # Esperar a que botones estén disponibles
        time.sleep(2)
        
        # Buscar todos los botones de detalle
        detail_buttons = []
        button_selectors = [
            "//a[contains(text(), 'Detalle')]",
            "//input[@value='Detalle']", 
            "//button[contains(text(), 'Detalle')]"
        ]
        
        for selector in button_selectors:
            try:
                buttons = driver.find_elements(By.XPATH, selector)
                detail_buttons.extend(buttons)
            except:
                continue
        
        logger.info(f"🔍 Botones Detalle encontrados: {len(detail_buttons)}")
        
        if not detail_buttons:
            return False
        
        # Probar cada botón hasta que uno funcione
        for idx, button in enumerate(detail_buttons):
            try:
                if button.is_displayed() and button.is_enabled():
                    logger.info(f"   Probando botón {idx + 1}")
                    
                    original_url = driver.current_url
                    
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                    time.sleep(1)
                    
                    try:
                        button.click()
                    except:
                        driver.execute_script("arguments[0].click();", button)
                    
                    time.sleep(4)
                    
                    new_url = driver.current_url
                    if new_url != original_url:
                        page_text = driver.find_element(By.TAG_NAME, "body").text
                        if "expediente" in page_text.lower() or "tasación" in page_text.lower():
                            logger.info(f"✅ NAVEGACIÓN EXITOSA con botón {idx + 1}")
                            return True
                        else:
                            driver.back()
                            time.sleep(3)
                            
            except Exception as e:
                logger.debug(f"Error con botón {idx + 1}: {e}")
                continue
        
        logger.error(f"❌ No se pudo navegar a detalle de remate {remate_numero}")
        return False
        
    except Exception as e:
        logger.error(f"Error en find_and_click_detail_button_simple: {e}")
        return False

def navigate_to_next_page(driver, target_page):
    """Navegación a siguiente página"""
    try:
        logger.info(f"🔄 Navegando a página {target_page}")
        time.sleep(2)  # Timer de 2 segundos como solicitado
        
        # Buscar enlace de página específica
        try:
            page_link = driver.find_element(By.XPATH, f"//a[text()='{target_page}']")
            if page_link.is_displayed():
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", page_link)
                time.sleep(1)
                
                try:
                    page_link.click()
                except:
                    driver.execute_script("arguments[0].click();", page_link)
                
                time.sleep(3)
                return True
                
        except Exception as e:
            logger.debug(f"No se encontró enlace a página {target_page}: {e}")
        
        # Buscar botón "Siguiente"
        try:
            next_selectors = [
                "//a[text()='»' or text()='>' or text()='Next' or text()='Siguiente']",
                "//input[@value='»' or @value='>' or @value='Next']",
                "//button[text()='»' or text()='>' or text()='Next']"
            ]
            
            for selector in next_selectors:
                try:
                    next_button = driver.find_element(By.XPATH, selector)
                    if next_button.is_displayed() and next_button.is_enabled():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                        time.sleep(1)
                        
                        try:
                            next_button.click()
                        except:
                            driver.execute_script("arguments[0].click();", next_button)
                        
                        time.sleep(3)
                        return True
                        
                except:
                    continue
                    
        except Exception as e:
            logger.debug(f"Error con botón siguiente: {e}")
        
        logger.error(f"❌ No se pudo navegar a página {target_page}")
        return False
        
    except Exception as e:
        logger.error(f"Error en navigate_to_next_page: {e}")
        return False

def scrape_all_pages_with_details():
    """Función principal para scraper todas las páginas con detalles"""
    driver = None
    url = "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml"
    
    try:
        logger.info("🚀 Iniciando scraping REMAJU - TODAS LAS PÁGINAS CON DETALLES")
        
        driver = setup_driver()
        driver.set_page_load_timeout(30)
        
        logger.info(f"Navegando a: {url}")
        driver.get(url)
        time.sleep(8)
        
        all_remates = []
        current_page = 1
        max_pages = 100
        failed_pages = 0
        max_failed = 3
        
        while current_page <= max_pages and failed_pages < max_failed:
            logger.info(f"\n📄 PROCESANDO PÁGINA {current_page} (Total remates: {len(all_remates)})")
            
            try:
                # Extraer remates básicos de la página actual
                remates_info = extract_basic_remate_info_only(driver)
                
                if remates_info:
                    failed_pages = 0  # Reset contador
                    
                    # Procesar cada remate
                    for i, remate_info in enumerate(remates_info):
                        remate_numero = remate_info['numero']
                        logger.info(f"  📋 REMATE {i+1}/{len(remates_info)} - Número {remate_numero}")
                        
                        try:
                            # Intentar extraer detalles
                            if find_and_click_detail_button_simple(driver, remate_numero):
                                logger.info(f"  ✅ Navegación exitosa a detalle")
                                
                                # Extraer información detallada
                                detailed_info = extract_detail_page_info(driver)
                                
                                # Combinar información
                                complete_remate = {
                                    **remate_info,
                                    **detailed_info,
                                    "procesado_detalle": True,
                                    "pagina": current_page,
                                    "index_global": len(all_remates) + 1,
                                    "timestamp_detalle": datetime.now().isoformat()
                                }
                                
                                all_remates.append(complete_remate)
                                logger.info(f"  ✅ Remate {remate_numero} procesado completamente")
                                
                                # Regresar a página principal
                                driver.back()
                                time.sleep(3)
                                
                            else:
                                # Agregar remate básico sin detalles
                                remate_info.update({
                                    "procesado_detalle": False,
                                    "error_detalle": "No se pudo acceder a detalle",
                                    "pagina": current_page,
                                    "index_global": len(all_remates) + 1
                                })
                                all_remates.append(remate_info)
                                logger.warning(f"  ⚠️ Remate {remate_numero} sin detalles")
                            
                            time.sleep(1)  # Pausa entre remates
                            
                        except Exception as e:
                            logger.error(f"  ❌ Error procesando remate {remate_numero}: {e}")
                            remate_info.update({
                                "procesado_detalle": False,
                                "error_detalle": str(e),
                                "pagina": current_page,
                                "index_global": len(all_remates) + 1
                            })
                            all_remates.append(remate_info)
                    
                    logger.info(f"✅ PÁGINA {current_page}: {len(remates_info)} remates procesados")
                    
                else:
                    logger.warning(f"⚠️ Página {current_page}: Sin remates encontrados")
                    failed_pages += 1
                
                # Navegar a siguiente página
                if navigate_to_next_page(driver, current_page + 1):
                    current_page += 1
                else:
                    logger.error(f"❌ No se pudo navegar a página {current_page + 1}")
                    failed_pages += 1
                    break
                    
            except Exception as e:
                logger.error(f"❌ Error en página {current_page}: {e}")
                failed_pages += 1
                break
        
        # Estadísticas finales
        remates_con_detalle = len([r for r in all_remates if r.get('procesado_detalle', False)])
        remates_con_precio = len([r for r in all_remates if r.get('precio_base_numerico', 0) > 0])
        
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
                "completitud_detalle_pct": round((remates_con_detalle/len(all_remates)*100) if all_remates else 0, 1),
                "completitud_precio_pct": round((remates_con_precio/len(all_remates)*100) if all_remates else 0, 1)
            },
            "remates": all_remates
        }
        
        # Guardar resultado
        output_file = "remates_result_fixed.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        logger.info(f"🎯 SCRAPING COMPLETADO:")
        logger.info(f"   📊 TOTAL REMATES: {len(all_remates)}")
        logger.info(f"   📄 PÁGINAS: {current_page - 1}")
        logger.info(f"   ✅ CON DETALLE: {remates_con_detalle}")
        logger.info(f"   💰 CON PRECIO: {remates_con_precio}")
        
        print(f"total_remates={len(all_remates)}")
        print(f"remates_con_detalle={remates_con_detalle}")
        print(f"total_pages={current_page - 1}")
        print(f"status=success")
        
        return resultado
        
    except Exception as e:
        logger.error(f"❌ Error general: {e}")
        print(f"status=error")
        return {"status": "error", "error": str(e)}
        
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    result = scrape_all_pages_with_details()
    print("=" * 60)
    print(f"RESULTADO FINAL: {result.get('status')}")
    if 'resumen' in result:
        print(f"🎯 TOTAL REMATES: {result['resumen']['total_remates']}")
        print(f"📄 PÁGINAS: {result['resumen']['paginas_procesadas']}")
        print(f"✅ CON DETALLE: {result['resumen']['remates_con_detalle']}")
        print(f"💰 CON PRECIO: {result['resumen']['remates_con_precio']}")
        print(f"📈 COMPLETITUD: {result['resumen']['completitud_detalle_pct']}%")
