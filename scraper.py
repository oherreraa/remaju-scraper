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

def extract_precio_from_lines(lines):
    """Extraer precio de las líneas de texto"""
    precio_data = {"moneda": "", "monto": "", "monto_numerico": 0}
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Buscar línea "Precio Base"
        if "precio base" in line.lower():
            # La siguiente línea debería tener el precio
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if "s/." in next_line or "$" in next_line:
                    precio_data["moneda"] = "PEN" if "s/." in next_line else "USD"
                    precio_data["monto"] = next_line
                    
                    # Extraer número
                    numbers = re.findall(r'[\d,]+\.?\d*', next_line.replace(',', ''))
                    if numbers:
                        try:
                            precio_data["monto_numerico"] = float(numbers[0])
                        except:
                            pass
        
        # También buscar directamente líneas con precio
        elif ("s/." in line or "$" in line) and any(c.isdigit() for c in line):
            if not precio_data["monto"]:
                precio_data["moneda"] = "PEN" if "s/." in line else "USD"
                precio_data["monto"] = line
                
                numbers = re.findall(r'[\d,]+\.?\d*', line.replace(',', ''))
                if numbers:
                    try:
                        precio_data["monto_numerico"] = float(numbers[0])
                    except:
                        pass
    
    return precio_data

def extract_remates_clean(driver):
    """Extraer remates con estructura limpia y sin redundancias"""
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        
        remates = []
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Detectar inicio de remate
            if "remate n°" in line.lower() and "convocatoria" in line.lower():
                
                # Estructura limpia - solo campos esenciales
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
                
                # Extraer información de precio
                precio_info = extract_precio_from_lines(remate_lines)
                remate["precio_moneda"] = precio_info["moneda"]
                remate["precio_monto"] = precio_info["monto"]
                remate["precio_numerico"] = precio_info["monto_numerico"]
                
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

def get_total_available_pages(driver):
    """Obtener el total de páginas disponibles"""
    try:
        # Buscar todos los enlaces de paginación
        page_links = driver.find_elements(By.XPATH, "//a[text()>='1' and text()<='100']")
        page_numbers = []
        
        for link in page_links:
            try:
                page_num = int(link.text)
                page_numbers.append(page_num)
            except:
                continue
        
        if page_numbers:
            max_page = max(page_numbers)
            logger.info(f"📄 Máximo número de página detectado: {max_page}")
            return max_page
        
        # Método alternativo: buscar en el texto de la página
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        # Buscar "Total: X registros"
        total_match = re.search(r'total:\s*(\d+)\s*registros', page_text.lower())
        if total_match:
            total_records = int(total_match.group(1))
            estimated_pages = (total_records // 4) + 1  # 4 remates por página aprox
            logger.info(f"📊 Total registros: {total_records}, páginas estimadas: {estimated_pages}")
            return estimated_pages
        
        logger.warning("No se pudo determinar el total de páginas")
        return 100  # Valor por defecto conservador
        
    except Exception as e:
        logger.warning(f"Error determinando total de páginas: {e}")
        return 100

def scrape_all_pages_improved(driver):
    """Scraper mejorado para obtener TODAS las páginas"""
    all_remates = []
    current_page = 1
    max_pages = get_total_available_pages(driver)
    consecutive_failures = 0
    max_consecutive_failures = 5
    
    logger.info(f"🚀 Iniciando scraping completo - estimado hasta página {max_pages}")
    
    while current_page <= max_pages and consecutive_failures < max_consecutive_failures:
        logger.info(f"📄 Procesando página {current_page}/{max_pages} " +
                   f"(Total remates: {len(all_remates)})")
        
        # Esperar carga mínima
        time.sleep(2)
        
        # Extraer remates de la página actual
        page_remates = extract_remates_clean(driver)
        
        if page_remates:
            consecutive_failures = 0  # Reset contador
            
            # Agregar metadata
            for idx, remate in enumerate(page_remates):
                remate['pagina'] = current_page
                remate['index_global'] = len(all_remates) + idx + 1
                remate['scraped_at'] = datetime.now().isoformat()
            
            all_remates.extend(page_remates)
            logger.info(f"✅ Página {current_page}: {len(page_remates)} remates " +
                       f"(Acumulado: {len(all_remates)})")
        else:
            consecutive_failures += 1
            logger.warning(f"❌ Página {current_page}: Sin datos " +
                         f"(Fallos consecutivos: {consecutive_failures})")
        
        # Si llegamos al máximo de fallos consecutivos
        if consecutive_failures >= max_consecutive_failures:
            logger.info(f"🏁 {max_consecutive_failures} páginas sin datos. Terminando scraping.")
            break
        
        # Navegar a la siguiente página
        navigation_success = False
        
        # Método 1: Buscar número específico de página siguiente
        try:
            next_page_num = current_page + 1
            next_link = driver.find_element(By.XPATH, f"//a[text()='{next_page_num}']")
            if next_link.is_displayed():
                classes = next_link.get_attribute('class') or ''
                if 'disabled' not in classes.lower() and 'inactive' not in classes.lower():
                    logger.info(f"🔄 Navegando a página {next_page_num}")
                    
                    # Scroll al elemento primero
                    driver.execute_script("arguments[0].scrollIntoView(true);", next_link)
                    time.sleep(1)
                    
                    # Clic
                    next_link.click()
                    navigation_success = True
        except Exception as e:
            logger.debug(f"Método 1 falló: {e}")
        
        # Método 2: Buscar botón "N" (Next)
        if not navigation_success:
            try:
                next_btn = driver.find_element(By.XPATH, "//a[text()='N']")
                if next_btn.is_displayed():
                    classes = next_btn.get_attribute('class') or ''
                    if 'disabled' not in classes.lower():
                        logger.info("🔄 Usando botón 'N' para navegar")
                        driver.execute_script("arguments[0].scrollIntoView(true);", next_btn)
                        time.sleep(1)
                        next_btn.click()
                        navigation_success = True
            except Exception as e:
                logger.debug(f"Método 2 falló: {e}")
        
        # Método 3: JavaScript para ir a página específica
        if not navigation_success:
            try:
                next_page_num = current_page + 1
                logger.info(f"🔄 Intentando navegación JavaScript a página {next_page_num}")
                
                # Buscar función de paginación en JavaScript
                js_nav_scripts = [
                    f"window.location.href = window.location.href.replace(/page=\\d+/, 'page={next_page_num}');",
                    f"document.querySelector('a[onclick*=\"page={next_page_num}\"]').click();",
                    f"PrimeFaces.ab({{source:'paginatorNext',process:'@this'}});",  # JSF común
                ]
                
                for script in js_nav_scripts:
                    try:
                        driver.execute_script(script)
                        navigation_success = True
                        break
                    except:
                        continue
                        
            except Exception as e:
                logger.debug(f"Método 3 falló: {e}")
        
        # Si ningún método funcionó
        if not navigation_success:
            logger.warning(f"⚠️ No se pudo navegar desde página {current_page}")
            
            # Último intento: buscar cualquier enlace que parezca "siguiente"
            try:
                possible_next = driver.find_elements(By.XPATH, 
                    "//a[contains(text(), '>') or contains(text(), '»') or contains(@title, 'next') or contains(@title, 'siguiente')]")
                
                for link in possible_next:
                    if link.is_displayed():
                        logger.info("🔄 Usando enlace 'siguiente' genérico")
                        link.click()
                        navigation_success = True
                        break
            except:
                pass
        
        # Si definitivamente no pudimos navegar
        if not navigation_success:
            logger.info(f"🏁 No se puede navegar más allá de página {current_page}. Terminando.")
            break
        
        current_page += 1
        
        # Esperar que cargue la nueva página
        time.sleep(3)
        
        # Verificar que efectivamente cambiamos de página
        try:
            new_page_data = extract_remates_clean(driver)
            if page_remates and new_page_data and page_remates == new_page_data:
                logger.warning("⚠️ Los datos son idénticos a la página anterior")
                consecutive_failures += 1
        except:
            pass
    
    return all_remates, current_page - 1

def scrape_remaju():
    """Función principal optimizada para obtener TODOS los remates"""
    driver = None
    url = "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml"
    
    try:
        logger.info("🚀 Iniciando scraping completo de REMAJU")
        
        driver = setup_driver()
        driver.set_page_load_timeout(30)
        
        logger.info(f"Navegando a: {url}")
        driver.get(url)
        time.sleep(6)
        
        page_title = driver.title
        logger.info(f"Título: {page_title}")
        
        # Scraping completo
        all_remates, total_pages = scrape_all_pages_improved(driver)
        
        # Estadísticas
        remates_con_precio = len([r for r in all_remates if r.get('precio_numerico', 0) > 0])
        remates_con_descripcion = len([r for r in all_remates if r.get('descripcion', '').strip()])
        
        # Resultado final limpio
        resultado = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "url": url,
            "resumen": {
                "total_remates": len(all_remates),
                "paginas_procesadas": total_pages,
                "remates_con_precio": remates_con_precio,
                "remates_con_descripcion": remates_con_descripcion,
                "completitud_precio_pct": round((remates_con_precio/len(all_remates)*100) if all_remates else 0, 1),
                "completitud_descripcion_pct": round((remates_con_descripcion/len(all_remates)*100) if all_remates else 0, 1)
            },
            "remates": all_remates
        }
        
        # Guardar resultado
        output_file = "remates_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ SCRAPING COMPLETADO:")
        logger.info(f"   📊 Total remates: {len(all_remates)}")
        logger.info(f"   📄 Páginas: {total_pages}")
        logger.info(f"   💰 Con precio: {remates_con_precio}")
        logger.info(f"   📝 Con descripción: {remates_con_descripcion}")
        
        # Outputs
        print(f"total_remates={len(all_remates)}")
        print(f"total_pages={total_pages}")
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
    print(f"RESULTADO: {result.get('status')}")
    if 'resumen' in result:
        print(f"REMATES: {result['resumen']['total_remates']}")
        print(f"PÁGINAS: {result['resumen']['paginas_procesadas']}")
        print(f"CON PRECIO: {result['resumen']['remates_con_precio']}")
