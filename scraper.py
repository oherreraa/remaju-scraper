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

def change_to_more_results_per_page(driver):
    """Cambiar a mostrar más resultados por página (12 en lugar de 4)"""
    try:
        logger.info("Intentando cambiar a 12 resultados por página...")
        
        # Buscar el dropdown "Rows Per Page"
        selectors = [
            "//select[contains(@class, 'rows')]",
            "//select[following-sibling::text()[contains(., 'Per Page')]]",
            "//select[preceding-sibling::text()[contains(., 'Rows')]]",
            "//select[contains(@onchange, 'rows')]",
            "//select[contains(@name, 'rows')]"
        ]
        
        for selector in selectors:
            try:
                select_element = driver.find_element(By.XPATH, selector)
                if select_element.is_displayed():
                    # Buscar opción de 12
                    options = select_element.find_elements(By.TAG_NAME, "option")
                    for option in options:
                        if option.text.strip() == "12":
                            logger.info("✅ Cambiando a 12 resultados por página")
                            option.click()
                            time.sleep(5)  # Esperar que recargue
                            return True
            except:
                continue
        
        # Método alternativo: buscar directamente la opción 12
        try:
            option_12 = driver.find_element(By.XPATH, "//option[@value='12' or text()='12']")
            if option_12.is_displayed():
                logger.info("✅ Encontrada opción 12, seleccionando...")
                option_12.click()
                time.sleep(5)
                return True
        except:
            pass
        
        logger.warning("No se pudo cambiar a 12 resultados por página")
        return False
        
    except Exception as e:
        logger.warning(f"Error cambiando resultados por página: {e}")
        return False

def extract_remates_clean(driver):
    """Extraer remates con estructura limpia"""
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        
        remates = []
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Detectar inicio de remate
            if "remate n°" in line.lower() and "convocatoria" in line.lower():
                
                # Estructura limpia
                remate = {
                    "numero_remate": "",
                    "numero": "",
                    "tipo_convocatoria": "",
                    "tipo_remate": "",
                    "ubicacion": "",
                    "fecha": "",
                    "hora": "",
                    "estado": "",
                    "descripcion": "",
                    "tipo_inmueble": "",
                    "area": "",
                    "precio_moneda": "",
                    "precio_monto": "",
                    "precio_numerico": 0,
                    "partida_registral": "",
                    "zona_registral": ""
                }
                
                # Extraer número de remate
                numero_match = re.search(r'remate n°?\s*(\d+)', line.lower())
                if numero_match:
                    remate["numero"] = numero_match.group(1)
                
                remate["numero_remate"] = line
                
                # Extraer tipo de convocatoria
                if "primera convocatoria" in line.lower():
                    remate["tipo_convocatoria"] = "PRIMERA"
                elif "segunda convocatoria" in line.lower():
                    remate["tipo_convocatoria"] = "SEGUNDA"
                
                # Recopilar líneas del remate actual
                remate_lines = []
                j = i + 1
                
                # Recopilar hasta el siguiente remate
                while j < len(lines):
                    next_line = lines[j].strip()
                    
                    # Parar si encontramos otro remate
                    if "remate n°" in next_line.lower() and "convocatoria" in next_line.lower():
                        break
                    
                    # Parar en las líneas finales (Seguimiento, Detalle, Aviso)
                    if next_line.lower() in ["seguimiento", "detalle", "aviso"]:
                        # Consumir todas estas líneas finales
                        while j < len(lines) and lines[j].strip().lower() in ["seguimiento", "detalle", "aviso"]:
                            j += 1
                        break
                    
                    remate_lines.append(next_line)
                    j += 1
                
                # Procesar líneas extraídas
                for idx, rline in enumerate(remate_lines):
                    rline = rline.strip()
                    
                    # Tipo de remate (primera línea)
                    if idx == 0 and ("remate" in rline.lower() or "simple" in rline.lower()):
                        remate["tipo_remate"] = rline
                    
                    # Ubicación (segunda línea, generalmente en mayúsculas)
                    elif idx == 1 and len(rline) > 2 and rline.isupper():
                        remate["ubicacion"] = rline
                    
                    # Estados
                    elif "presentación de ofertas" in rline.lower():
                        remate["estado"] = rline
                    
                    # Fechas (formato dd/mm/yyyy)
                    elif re.match(r'\d{2}/\d{2}/\d{4}', rline):
                        remate["fecha"] = rline
                    
                    # Horas (formato hh:mm AM/PM)
                    elif re.match(r'\d{1,2}:\d{2}\s*(AM|PM)', rline):
                        remate["hora"] = rline
                    
                    # Precio
                    elif "precio base" in rline.lower():
                        # Siguiente línea debería tener el precio
                        if idx + 1 < len(remate_lines):
                            next_price_line = remate_lines[idx + 1].strip()
                            if "s/." in next_price_line or "$" in next_price_line:
                                remate["precio_moneda"] = "PEN" if "s/." in next_price_line else "USD"
                                remate["precio_monto"] = next_price_line
                                
                                # Extraer número
                                numbers = re.findall(r'[\d,]+\.?\d*', next_price_line.replace(',', ''))
                                if numbers:
                                    try:
                                        remate["precio_numerico"] = float(numbers[0])
                                    except:
                                        pass
                    
                    # Precio directo (si no se encontró con "precio base")
                    elif ("s/." in rline or "$" in rline) and any(c.isdigit() for c in rline) and not remate["precio_monto"]:
                        remate["precio_moneda"] = "PEN" if "s/." in rline else "USD"
                        remate["precio_monto"] = rline
                        
                        numbers = re.findall(r'[\d,]+\.?\d*', rline.replace(',', ''))
                        if numbers:
                            try:
                                remate["precio_numerico"] = float(numbers[0])
                            except:
                                pass
                    
                    # Descripción del bien (líneas largas)
                    elif len(rline) > 50 and not any(keyword in rline.lower() for keyword in 
                                                   ['precio', 'seguimiento', 'detalle', 'aviso', 'remate', 'presentación']):
                        if not remate["descripcion"]:
                            remate["descripcion"] = rline
                            
                            # Extraer área del terreno
                            area_match = re.search(r'área.*?de\s*([\d,\.]+\s*m2?)', rline.lower())
                            if not area_match:
                                area_match = re.search(r'([\d,\.]+\s*m2)', rline.lower())
                            if area_match:
                                remate["area"] = area_match.group(1)
                            
                            # Extraer tipo de inmueble
                            tipos = ['casa', 'departamento', 'terreno', 'local', 'oficina', 'estacionamiento', 'depósito', 'galería']
                            for tipo in tipos:
                                if tipo in rline.lower():
                                    remate["tipo_inmueble"] = tipo.upper()
                                    break
                            
                            # Extraer partida registral
                            partida_match = re.search(r'partida.*?n[°º]?\s*([\d\-]+)', rline.lower())
                            if partida_match:
                                remate["partida_registral"] = partida_match.group(1)
                            
                            # Extraer zona registral
                            zona_match = re.search(r'zona registral.*?n[°º]?\s*([\w\s]+?)(?:\s*–|\s*-|$)', rline.lower())
                            if zona_match:
                                remate["zona_registral"] = zona_match.group(1).strip()
                
                # Solo agregar si tiene datos esenciales
                if (remate["numero"] and 
                    (remate["descripcion"] or remate["ubicacion"] or remate["precio_monto"])):
                    
                    remates.append(remate)
                    logger.info(f"✅ Remate {remate['numero']}: {remate['ubicacion']} - {remate['precio_monto']}")
                
                # Continuar desde donde paramos
                i = j - 1  # -1 porque el loop principal hará i += 1
            
            i += 1
        
        logger.info(f"Página procesada: {len(remates)} remates")
        return remates
        
    except Exception as e:
        logger.error(f"Error en extract_remates_clean: {e}")
        return []

def navigate_to_next_page(driver, current_page):
    """Navegación robusta a la siguiente página"""
    next_page_num = current_page + 1
    
    logger.info(f"🔄 Intentando navegar de página {current_page} a {next_page_num}")
    
    # Método 1: Clic directo en número de página
    try:
        # Buscar enlace de la siguiente página
        next_page_link = driver.find_element(By.XPATH, f"//a[text()='{next_page_num}']")
        if next_page_link.is_displayed():
            classes = next_page_link.get_attribute('class') or ''
            if 'disabled' not in classes.lower() and 'inactive' not in classes.lower():
                # Scroll al elemento
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_page_link)
                time.sleep(1)
                
                # Clic
                driver.execute_script("arguments[0].click();", next_page_link)
                logger.info(f"✅ Navegación exitosa a página {next_page_num} (método directo)")
                return True
    except Exception as e:
        logger.debug(f"Método 1 falló: {e}")
    
    # Método 2: Buscar botón "N" (Next)
    try:
        next_btn = driver.find_element(By.XPATH, "//a[text()='N' or text()='»' or text()='>']")
        if next_btn.is_displayed():
            classes = next_btn.get_attribute('class') or ''
            if 'disabled' not in classes.lower():
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", next_btn)
                logger.info("✅ Navegación exitosa con botón 'N' (método 2)")
                return True
    except Exception as e:
        logger.debug(f"Método 2 falló: {e}")
    
    # Método 3: Buscar cualquier enlace con onclick que contenga paginación
    try:
        pagination_links = driver.find_elements(By.XPATH, "//a[contains(@onclick, 'page') or contains(@onclick, 'Page')]")
        for link in pagination_links:
            if link.is_displayed():
                onclick = link.get_attribute('onclick') or ''
                # Buscar si contiene el número de página que queremos
                if str(next_page_num) in onclick:
                    driver.execute_script("arguments[0].click();", link)
                    logger.info(f"✅ Navegación exitosa con onclick a página {next_page_num} (método 3)")
                    return True
    except Exception as e:
        logger.debug(f"Método 3 falló: {e}")
    
    # Método 4: JavaScript directo para cambiar página
    try:
        # Intentar diferentes funciones JavaScript comunes
        js_functions = [
            f"window.location.href = window.location.href + '&page={next_page_num}';",
            f"if(typeof(PrimeFaces) !== 'undefined') {{ PrimeFaces.ab({{source:'page{next_page_num}',process:'@this'}}); }}",
            f"if(typeof(changePage) === 'function') {{ changePage({next_page_num}); }}",
        ]
        
        for js_func in js_functions:
            try:
                driver.execute_script(js_func)
                logger.info(f"✅ Navegación exitosa con JavaScript a página {next_page_num} (método 4)")
                return True
            except:
                continue
    except Exception as e:
        logger.debug(f"Método 4 falló: {e}")
    
    # Método 5: Buscar INPUT de página y cambiarlo
    try:
        page_input = driver.find_element(By.XPATH, "//input[@type='text' and (@value='{0}' or @placeholder='página')]".format(current_page))
        if page_input.is_displayed():
            page_input.clear()
            page_input.send_keys(str(next_page_num))
            
            # Buscar botón "Go" o similar
            go_buttons = driver.find_elements(By.XPATH, "//button[text()='Go' or text()='Ir'] | //input[@type='submit' and @value='Go']")
            for btn in go_buttons:
                if btn.is_displayed():
                    btn.click()
                    logger.info(f"✅ Navegación exitosa con input de página {next_page_num} (método 5)")
                    return True
    except Exception as e:
        logger.debug(f"Método 5 falló: {e}")
    
    logger.warning(f"❌ No se pudo navegar a página {next_page_num}")
    return False

def scrape_all_pages_aggressive(driver):
    """Scraper agresivo para obtener TODOS los registros"""
    all_remates = []
    current_page = 1
    
    # Primero intentar cambiar a más resultados por página
    change_to_more_results_per_page(driver)
    
    # Límite de seguridad muy alto
    max_pages = 100
    pages_without_data = 0
    max_pages_without_data = 3
    
    logger.info(f"🚀 Iniciando scraping agresivo - hasta {max_pages} páginas")
    
    while current_page <= max_pages:
        logger.info(f"📄 Procesando página {current_page} (Total remates acumulados: {len(all_remates)})")
        
        # Esperar carga mínima
        time.sleep(1)
        
        # Extraer remates de la página actual
        page_remates = extract_remates_clean(driver)
        
        if page_remates:
            pages_without_data = 0  # Reset contador
            
            # Agregar metadata
            for idx, remate in enumerate(page_remates):
                remate['pagina'] = current_page
                remate['index_global'] = len(all_remates) + idx + 1
                remate['scraped_at'] = datetime.now().isoformat()
            
            all_remates.extend(page_remates)
            logger.info(f"✅ Página {current_page}: {len(page_remates)} remates " +
                       f"(Total acumulado: {len(all_remates)})")
        else:
            pages_without_data += 1
            logger.warning(f"❌ Página {current_page}: Sin datos " +
                         f"(Páginas consecutivas sin datos: {pages_without_data})")
            
            # Solo parar después de muchas páginas sin datos
            if pages_without_data >= max_pages_without_data:
                logger.info(f"🏁 {max_pages_without_data} páginas consecutivas sin datos. Finalizando.")
                break
        
        # Intentar navegar a siguiente página
        navigation_success = navigate_to_next_page(driver, current_page)
        
        if not navigation_success:
            logger.warning(f"⚠️ No se pudo navegar más allá de página {current_page}")
            break
        
        current_page += 1
        
        # Esperar que cargue la nueva página
        time.sleep(4)
        
        # Verificar que efectivamente cambió la página comparando contenido
        try:
            # Verificar si hay cambios en el contenido
            new_page_text = driver.find_element(By.TAG_NAME, "body").text
            if f"página {current_page - 1}" in new_page_text.lower() or f"page {current_page - 1}" in new_page_text.lower():
                logger.debug(f"Parece que navegamos correctamente a página {current_page}")
        except:
            pass
    
    return all_remates, current_page - 1

def scrape_remaju():
    """Función principal para obtener TODOS los remates de REMAJU"""
    driver = None
    url = "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml"
    
    try:
        logger.info("🚀 Iniciando scraping AGRESIVO de REMAJU para obtener TODOS los registros")
        
        driver = setup_driver()
        driver.set_page_load_timeout(30)
        
        logger.info(f"Navegando a: {url}")
        driver.get(url)
        time.sleep(8)  # Esperar más tiempo inicial
        
        page_title = driver.title
        logger.info(f"Título: {page_title}")
        
        # Scraping agresivo
        all_remates, total_pages = scrape_all_pages_aggressive(driver)
        
        # Estadísticas
        remates_con_precio = len([r for r in all_remates if r.get('precio_numerico', 0) > 0])
        remates_con_descripcion = len([r for r in all_remates if r.get('descripcion', '').strip()])
        
        # Resultado final
        resultado = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "url": url,
            "scraping_mode": "aggressive_all_pages",
            "resumen": {
                "total_remates": len(all_remates),
                "paginas_procesadas": total_pages,
                "remates_con_precio": remates_con_precio,
                "remates_con_descripcion": remates_con_descripcion,
                "promedio_por_pagina": round(len(all_remates) / total_pages if total_pages > 0 else 0, 1),
                "completitud_precio_pct": round((remates_con_precio/len(all_remates)*100) if all_remates else 0, 1),
                "completitud_descripcion_pct": round((remates_con_descripcion/len(all_remates)*100) if all_remates else 0, 1)
            },
            "remates": all_remates
        }
        
        # Guardar resultado
        output_file = "remates_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        logger.info(f"🎯 SCRAPING COMPLETADO CON ÉXITO:")
        logger.info(f"   📊 TOTAL REMATES: {len(all_remates)}")
        logger.info(f"   📄 PÁGINAS PROCESADAS: {total_pages}")
        logger.info(f"   💰 CON PRECIO: {remates_con_precio}")
        logger.info(f"   📝 CON DESCRIPCIÓN: {remates_con_descripcion}")
        logger.info(f"   📈 PROMEDIO POR PÁGINA: {round(len(all_remates) / total_pages if total_pages > 0 else 0, 1)}")
        
        # Outputs
        print(f"total_remates={len(all_remates)}")
        print(f"total_pages={total_pages}")
        print(f"promedio_por_pagina={round(len(all_remates) / total_pages if total_pages > 0 else 0, 1)}")
        print(f"status=success")
        
        return resultado
        
    except Exception as e:
        error_result = {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "url": url
        }
        
        with open('remates_result.json', 'w', encoding='utf-8') as f:
            json.dump(error_result, f, ensure_ascii=False, indent=2)
        
        logger.error(f"❌ Error: {e}")
        print(f"status=error")
        
        return error_result
        
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    result = scrape_remaju()
    print("=" * 60)
    print(f"RESULTADO FINAL: {result.get('status')}")
    if 'resumen' in result:
        print(f"🎯 TOTAL REMATES OBTENIDOS: {result['resumen']['total_remates']}")
        print(f"📄 PÁGINAS PROCESADAS: {result['resumen']['paginas_procesadas']}")
        print(f"💰 REMATES CON PRECIO: {result['resumen']['remates_con_precio']}")
        if result['resumen']['total_remates'] < 200:
            print("⚠️  ADVERTENCIA: Se esperaban ~267 registros")
        else:
            print("✅ SCRAPING COMPLETO EXITOSO")
