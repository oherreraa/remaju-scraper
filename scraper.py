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
        # Información del expediente
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
        
        # Información del remate
        "convocatoria": "",
        "tipo_cambio": "",
        "tasacion": "",
        "precio_base": "",
        "precio_base_numerico": 0,
        "precio_base_moneda": "",
        "incremento_ofertas": "",
        "arancel": "",
        "oblaje": "",
        "descripcion_completa": "",
        "num_inscritos": ""
    }
    
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        
        # Procesar líneas buscando patrones específicos
        for i, line in enumerate(lines):
            
            # Información del expediente
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
            
            # Información del remate
            elif line == "Convocatoria" and i + 1 < len(lines):
                remate_data["convocatoria"] = lines[i + 1]
            elif line == "Tipo Cambio" and i + 1 < len(lines):
                remate_data["tipo_cambio"] = lines[i + 1]
            elif line == "Tasación" and i + 1 < len(lines):
                remate_data["tasacion"] = lines[i + 1]
            elif line == "Precio Base" and i + 1 < len(lines):
                precio_base = lines[i + 1]
                remate_data["precio_base"] = precio_base
                
                # Extraer valor numérico y moneda
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
        "inmueble_distrito_judicial": "",
        "inmueble_departamento": "",
        "inmueble_provincia": "",
        "inmueble_distrito": "",
        "inmueble_partida_registral": "",
        "inmueble_tipo": "",
        "inmueble_direccion": "",
        "inmueble_cargas_gravamenes": "",
        "inmueble_porcentaje_rematar": "",
        "inmueble_imagenes": ""
    }
    
    try:
        # Intentar hacer clic en la pestaña Inmuebles
        try:
            inmuebles_tab = driver.find_element(By.XPATH, "//a[contains(text(), 'Inmuebles') or contains(@href, 'inmuebles') or contains(@onclick, 'inmuebles')]")
            driver.execute_script("arguments[0].click();", inmuebles_tab)
            time.sleep(3)
            logger.info("✅ Navegó a pestaña Inmuebles")
        except:
            logger.warning("⚠️ No se pudo hacer clic en pestaña Inmuebles, extrayendo de página actual")
        
        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        
        # Buscar información específica de inmuebles
        for i, line in enumerate(lines):
            if line == "Distrito Judicial" and i + 1 < len(lines):
                inmuebles_data["inmueble_distrito_judicial"] = lines[i + 1]
            elif line == "Departamento" and i + 1 < len(lines):
                inmuebles_data["inmueble_departamento"] = lines[i + 1]
            elif line == "Provincia" and i + 1 < len(lines):
                inmuebles_data["inmueble_provincia"] = lines[i + 1]
            elif line == "Distrito" and i + 1 < len(lines):
                inmuebles_data["inmueble_distrito"] = lines[i + 1]
        
        # Buscar información de tabla de inmuebles
        try:
            table_text = driver.find_element(By.TAG_NAME, "body").text
            
            # Extraer partida registral
            partida_match = re.search(r'(P?\d{8,})', table_text)
            if partida_match:
                inmuebles_data["inmueble_partida_registral"] = partida_match.group(1)
            
            # Extraer tipo de inmueble
            tipos_inmuebles = ['CASA', 'DEPARTAMENTO', 'TERRENO', 'LOCAL', 'OFICINA', 'EDIFICIO']
            for tipo in tipos_inmuebles:
                if tipo in table_text.upper():
                    inmuebles_data["inmueble_tipo"] = tipo
                    break
            
            # Extraer dirección (buscar línea larga con ubicación)
            direccion_matches = re.findall(r'[A-Z][A-Z\s\.,]+MZ[^\.]+\.', table_text)
            if direccion_matches:
                inmuebles_data["inmueble_direccion"] = direccion_matches[0].strip()
            
            # Extraer cargas y gravámenes
            cargas_section = re.search(r'HIPOTECA.*?ESCRITURA[^\.]*\.', table_text, re.DOTALL)
            if cargas_section:
                inmuebles_data["inmueble_cargas_gravamenes"] = cargas_section.group(0)
            
            # Extraer porcentaje a rematar
            porcentaje_match = re.search(r'(\d+\s*%)', table_text)
            if porcentaje_match:
                inmuebles_data["inmueble_porcentaje_rematar"] = porcentaje_match.group(1)
            
        except Exception as e:
            logger.debug(f"Error extrayendo tabla de inmuebles: {e}")
        
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
        # Intentar hacer clic en la pestaña Cronograma
        try:
            cronograma_tab = driver.find_element(By.XPATH, "//a[contains(text(), 'Cronograma') or contains(@href, 'cronograma') or contains(@onclick, 'cronograma')]")
            driver.execute_script("arguments[0].click();", cronograma_tab)
            time.sleep(3)
            logger.info("✅ Navegó a pestaña Cronograma")
        except:
            logger.warning("⚠️ No se pudo hacer clic en pestaña Cronograma, extrayendo de página actual")
        
        page_text = driver.find_element(By.TAG_NAME, "body").text
        cronograma_data["cronograma_texto_completo"] = page_text
        
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        
        # Extraer fases del cronograma
        fases = []
        
        for line in lines:
            # Buscar líneas que empiecen con número (fases)
            if re.match(r'^\d+[A-Za-z]', line):
                fase = {
                    "linea_completa": line
                }
                
                # Extraer número de fase
                numero_match = re.match(r'^(\d+)', line)
                if numero_match:
                    fase["numero"] = numero_match.group(1)
                
                # Extraer nombre de fase
                partes = line.split()
                if len(partes) > 1:
                    fase["fase_nombre"] = partes[1]
                
                # Extraer fechas (formato dd/mm/yyyy)
                fechas = re.findall(r'\d{2}/\d{2}/\d{4}', line)
                if len(fechas) >= 2:
                    fase["fecha_inicio"] = fechas[0]
                    fase["fecha_fin"] = fechas[1]
                
                # Extraer horas
                horas = re.findall(r'\d{2}:\d{2}:\d{2}\s*[AP]M', line)
                if len(horas) >= 2:
                    fase["hora_inicio"] = horas[0]
                    fase["hora_fin"] = horas[1]
                
                fases.append(fase)
        
        cronograma_data["cronograma_fases"] = fases
        
        logger.info(f"✅ Pestaña CRONOGRAMA: {len(fases)} fases extraídas")
        
    except Exception as e:
        logger.error(f"Error en extract_cronograma_tab_info: {e}")
    
    return cronograma_data

def extract_detail_page_info(driver):
    """Extraer toda la información de la página de detalle con las 3 pestañas"""
    detail_data = {}
    
    try:
        # Esperar a que cargue completamente
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        logger.info("📋 Extrayendo información de pestaña REMATE")
        
        # PESTAÑA 1: REMATE (información principal)
        remate_info = extract_remate_tab_info(driver)
        detail_data.update(remate_info)
        
        # PESTAÑA 2: INMUEBLES
        logger.info("🏠 Navegando a pestaña INMUEBLES")
        inmuebles_info = extract_inmuebles_tab_info(driver)
        detail_data.update(inmuebles_info)
        
        # PESTAÑA 3: CRONOGRAMA
        logger.info("📅 Navegando a pestaña CRONOGRAMA")
        cronograma_info = extract_cronograma_tab_info(driver)
        detail_data.update(cronograma_info)
        
        logger.info("✅ Información completa extraída de las 3 pestañas")
        return detail_data
        
    except Exception as e:
        logger.error(f"Error extrayendo información de detalle: {e}")
        return detail_data

def extract_basic_remate_info(driver):
    """Extraer información básica de remates de la página actual"""
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        
        remates = []
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Detectar inicio de remate
            if "remate n°" in line.lower() and "convocatoria" in line.lower():
                
                remate = {
                    "numero_remate": line,
                    "numero": "",
                    "tipo_convocatoria": "",
                }
                
                # Extraer número de remate
                numero_match = re.search(r'remate n°?\s*(\d+)', line.lower())
                if numero_match:
                    remate["numero"] = numero_match.group(1)
                
                # Extraer tipo de convocatoria
                if "primera convocatoria" in line.lower():
                    remate["tipo_convocatoria"] = "PRIMERA"
                elif "segunda convocatoria" in line.lower():
                    remate["tipo_convocatoria"] = "SEGUNDA"
                elif "tercera convocatoria" in line.lower():
                    remate["tipo_convocatoria"] = "TERCERA"
                
                # Solo agregar si tiene número
                if remate["numero"]:
                    remates.append(remate)
                    logger.info(f"📋 Remate básico encontrado: {remate['numero']} - {remate['tipo_convocatoria']}")
            
            i += 1
        
        logger.info(f"📄 Encontrados {len(remates)} remates básicos en la página")
        return remates
        
    except Exception as e:
        logger.error(f"Error en extract_basic_remate_info: {e}")
        return []

def find_and_click_detail_button(driver, remate_numero):
    """Encontrar y hacer clic en el botón de detalle específico"""
    try:
        logger.info(f"🔍 Buscando botón detalle para remate {remate_numero}")
        
        # Estrategias múltiples para encontrar el botón
        detail_button_selectors = [
            f"//a[contains(text(), 'Detalle') or contains(text(), 'DETALLE')]",
            f"//input[@value='Detalle' or @value='DETALLE']",
            f"//button[contains(text(), 'Detalle')]",
            f"//span[contains(text(), 'Detalle')]/parent::*",
            f"//td[contains(text(), '{remate_numero}')]/following-sibling::td//a",
            f"//*[contains(text(), '{remate_numero}')]/following-sibling::*//a[contains(text(), 'Detalle')]"
        ]
        
        for selector in detail_button_selectors:
            try:
                detail_buttons = driver.find_elements(By.XPATH, selector)
                logger.info(f"Encontrados {len(detail_buttons)} botones con selector")
                
                for idx, button in enumerate(detail_buttons):
                    try:
                        if button.is_displayed() and button.is_enabled():
                            
                            # Buscar contexto del remate
                            button_context = ""
                            try:
                                # Buscar en la fila de tabla
                                row = button.find_element(By.XPATH, "./ancestor::tr[1]")
                                button_context = row.text
                            except:
                                try:
                                    # Buscar en div contenedor
                                    container = button.find_element(By.XPATH, "./ancestor::div[contains(@class, 'panel') or contains(@class, 'card')][1]")
                                    button_context = container.text
                                except:
                                    # Usar área general alrededor del botón
                                    parent = button.find_element(By.XPATH, "./..")
                                    button_context = parent.text
                            
                            logger.info(f"Botón {idx + 1} contexto: {button_context[:100]}...")
                            
                            if remate_numero in button_context:
                                logger.info(f"✅ MATCH! Botón para remate {remate_numero} encontrado")
                                
                                # Scroll y clic
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                time.sleep(2)
                                
                                try:
                                    button.click()
                                    logger.info(f"🖱️ Clic normal exitoso")
                                except:
                                    driver.execute_script("arguments[0].click();", button)
                                    logger.info(f"🖱️ Clic JavaScript exitoso")
                                
                                # Verificar navegación esperando cambio de URL
                                time.sleep(5)
                                current_url = driver.current_url
                                logger.info(f"URL después del clic: {current_url}")
                                
                                # Verificar que estamos en página de detalle
                                if "detalle" in current_url.lower() or driver.current_url != "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml":
                                    return True
                    
                    except Exception as e:
                        logger.debug(f"Error procesando botón {idx}: {e}")
                        continue
            
            except Exception as e:
                logger.debug(f"Error con selector {selector}: {e}")
                continue
        
        logger.warning(f"❌ No se encontró botón detalle para remate {remate_numero}")
        return False
        
    except Exception as e:
        logger.error(f"Error en find_and_click_detail_button: {e}")
        return False

def extract_remates_with_details_first_page(driver):
    """Extraer remates con información detallada - SOLO PRIMERA PÁGINA"""
    try:
        logger.info("🚀 Iniciando extracción con detalles - SOLO PRIMERA PÁGINA")
        
        # Primero extraer información básica de todos los remates en la página
        basic_remates = extract_basic_remate_info(driver)
        
        if not basic_remates:
            logger.error("❌ No se encontraron remates básicos")
            return []
        
        detailed_remates = []
        
        # Procesar solo los primeros 3 remates para prueba
        max_remates = min(3, len(basic_remates))
        logger.info(f"📊 Procesando {max_remates} remates de {len(basic_remates)} encontrados")
        
        for i, basic_remate in enumerate(basic_remates[:max_remates]):
            remate_numero = basic_remate['numero']
            logger.info(f"\n📄 PROCESANDO DETALLE {i+1}/{max_remates}: Remate {remate_numero}")
            
            try:
                # Intentar hacer clic en el botón de detalle
                if find_and_click_detail_button(driver, remate_numero):
                    logger.info(f"✅ Navegación exitosa a detalle de remate {remate_numero}")
                    
                    # Extraer información detallada
                    detailed_info = extract_detail_page_info(driver)
                    
                    # Combinar información básica con detallada
                    complete_remate = {
                        **basic_remate,
                        **detailed_info,
                        "procesado_detalle": True,
                        "timestamp_detalle": datetime.now().isoformat(),
                        "link_directo": f"https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml?id={remate_numero}"
                    }
                    
                    detailed_remates.append(complete_remate)
                    logger.info(f"✅ Remate {remate_numero} procesado completamente")
                    
                    # Regresar a la página anterior
                    logger.info(f"🔙 Regresando a página principal")
                    driver.back()
                    time.sleep(4)
                    
                    # Verificar que regresamos correctamente
                    if "remateExterno" in driver.current_url:
                        logger.info(f"✅ Regreso exitoso a página principal")
                    else:
                        logger.warning(f"⚠️ Posible problema en el regreso - navegando manualmente")
                        driver.get("https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml")
                        time.sleep(5)
                    
                else:
                    logger.error(f"❌ No se pudo navegar a detalle de remate {remate_numero}")
                    # Agregar remate básico sin detalles
                    basic_remate["procesado_detalle"] = False
                    basic_remate["error_detalle"] = "No se encontró botón detalle"
                    detailed_remates.append(basic_remate)
                
                # Pausa entre remates
                time.sleep(3)
                
            except Exception as e:
                logger.error(f"❌ Error procesando remate {remate_numero}: {e}")
                # Agregar remate básico con error
                basic_remate["procesado_detalle"] = False
                basic_remate["error_detalle"] = str(e)
                detailed_remates.append(basic_remate)
        
        logger.info(f"🎯 PROCESAMIENTO COMPLETADO: {len(detailed_remates)} remates procesados")
        return detailed_remates
        
    except Exception as e:
        logger.error(f"Error en extract_remates_with_details_first_page: {e}")
        return []

def scrape_remaju_with_details():
    """Función principal con extracción de detalles - SOLO PRIMERA PÁGINA"""
    driver = None
    url = "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml"
    
    try:
        logger.info("🚀 Iniciando scraping REMAJU con extracción de detalles - PRIMERA PÁGINA")
        
        driver = setup_driver()
        driver.set_page_load_timeout(30)
        
        logger.info(f"Navegando a: {url}")
        driver.get(url)
        time.sleep(8)
        
        page_title = driver.title
        logger.info(f"Título: {page_title}")
        
        # Scraping con detalles
        all_remates = extract_remates_with_details_first_page(driver)
        
        # Estadísticas
        remates_con_detalle = len([r for r in all_remates if r.get('procesado_detalle', False)])
        remates_con_precio = len([r for r in all_remates if r.get('precio_base_numerico', 0) > 0])
        
        # Resultado final
        resultado = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "url": url,
            "scraping_mode": "detailed_extraction_first_page",
            "resumen": {
                "total_remates": len(all_remates),
                "remates_con_detalle": remates_con_detalle,
                "remates_con_precio": remates_con_precio,
                "pagina_procesada": 1,
                "completitud_detalle_pct": round((remates_con_detalle/len(all_remates)*100) if all_remates else 0, 1),
                "completitud_precio_pct": round((remates_con_precio/len(all_remates)*100) if all_remates else 0, 1)
            },
            "remates": all_remates
        }
        
        # Guardar resultado
        output_file = "remates_result_detailed.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        logger.info(f"🎯 SCRAPING COMPLETADO:")
        logger.info(f"   📊 TOTAL REMATES: {len(all_remates)}")
        logger.info(f"   ✅ CON DETALLE: {remates_con_detalle}")
        logger.info(f"   💰 CON PRECIO: {remates_con_precio}")
        logger.info(f"   📈 COMPLETITUD DETALLE: {round((remates_con_detalle/len(all_remates)*100) if all_remates else 0, 1)}%")
        
        # Outputs
        print(f"total_remates={len(all_remates)}")
        print(f"remates_con_detalle={remates_con_detalle}")
        print(f"status=success")
        
        return resultado
        
    except Exception as e:
        error_result = {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "url": url
        }
        
        with open('remates_result_detailed.json', 'w', encoding='utf-8') as f:
            json.dump(error_result, f, ensure_ascii=False, indent=2)
        
        logger.error(f"❌ Error: {e}")
        print(f"status=error")
        
        return error_result
        
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    result = scrape_remaju_with_details()
    print("=" * 60)
    print(f"RESULTADO FINAL: {result.get('status')}")
    if 'resumen' in result:
        print(f"🎯 TOTAL REMATES: {result['resumen']['total_remates']}")
        print(f"✅ CON DETALLE: {result['resumen']['remates_con_detalle']}")
        print(f"💰 CON PRECIO: {result['resumen']['remates_con_precio']}")
        print(f"📈 COMPLETITUD: {result['resumen']['completitud_detalle_pct']}%")
        if result['resumen']['remates_con_detalle'] > 0:
            print("🎉 EXTRACCIÓN DE DETALLES EXITOSA")
        else:
            print("⚠️  ADVERTENCIA: No se pudieron extraer detalles")
