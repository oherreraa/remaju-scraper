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
                    
                    # Precio directo
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

def get_page_signature(driver):
    """Obtener 'firma' única de la página actual para verificar cambios"""
    try:
        # Buscar números de remate únicos en la página
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        # Extraer todos los números de remate de la página
        remate_numbers = re.findall(r'remate n°?\s*(\d+)', page_text.lower())
        
        # Crear signature única basada en los números de remate
        if remate_numbers:
            signature = sorted(set(remate_numbers))  # Unique y ordenados
            return tuple(signature)  # Inmutable para comparación
        
        # Si no hay remates, usar texto parcial como signature
        return hash(page_text[:1000])  # Hash de primeros 1000 caracteres
        
    except Exception as e:
        logger.warning(f"Error obteniendo signature de página: {e}")
        return None

def navigate_and_verify(driver, current_page, target_page, current_signature):
    """Navegar y VERIFICAR que realmente cambió la página"""
    
    logger.info(f"🔄 Navegando de página {current_page} a {target_page}")
    
    # Método 1: Clic directo en número de página
    try:
        next_page_link = driver.find_element(By.XPATH, f"//a[text()='{target_page}']")
        if next_page_link.is_displayed():
            classes = next_page_link.get_attribute('class') or ''
            if 'disabled' not in classes.lower() and 'inactive' not in classes.lower():
                # Scroll y clic
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_page_link)
                time.sleep(1)
                
                # Intentar clic normal primero
                try:
                    next_page_link.click()
                except:
                    # Si falla, usar JavaScript
                    driver.execute_script("arguments[0].click();", next_page_link)
                
                # VERIFICACIÓN CRÍTICA: Esperar y verificar cambio
                logger.info(f"   Esperando cambio de página...")
                time.sleep(6)  # Tiempo generoso para AJAX
                
                new_signature = get_page_signature(driver)
                
                if new_signature and new_signature != current_signature:
                    logger.info(f"✅ NAVEGACIÓN VERIFICADA a página {target_page} (método directo)")
                    return True, new_signature
                else:
                    logger.warning(f"❌ Navegación FALLÓ - página no cambió (método directo)")
        
    except Exception as e:
        logger.debug(f"Método 1 falló: {e}")
    
    # Método 2: Botón Next con verificación
    try:
        next_btn = driver.find_element(By.XPATH, "//a[text()='N' or text()='»' or text()='>']")
        if next_btn.is_displayed():
            classes = next_btn.get_attribute('class') or ''
            if 'disabled' not in classes.lower():
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
                time.sleep(1)
                
                try:
                    next_btn.click()
                except:
                    driver.execute_script("arguments[0].click();", next_btn)
                
                logger.info(f"   Esperando cambio de página (método Next)...")
                time.sleep(6)
                
                new_signature = get_page_signature(driver)
                
                if new_signature and new_signature != current_signature:
                    logger.info(f"✅ NAVEGACIÓN VERIFICADA a página {target_page} (método Next)")
                    return True, new_signature
                else:
                    logger.warning(f"❌ Navegación FALLÓ - página no cambió (método Next)")
                    
    except Exception as e:
        logger.debug(f"Método 2 falló: {e}")
    
    # Método 3: Refresh y navegación directa via URL
    try:
        current_url = driver.current_url
        
        # Intentar agregar parámetros de página a la URL
        if '?' in current_url:
            new_url = f"{current_url}&page={target_page}"
        else:
            new_url = f"{current_url}?page={target_page}"
        
        logger.info(f"   Intentando navegación directa a: {new_url}")
        driver.get(new_url)
        time.sleep(8)  # Tiempo para cargar página completa
        
        new_signature = get_page_signature(driver)
        
        if new_signature and new_signature != current_signature:
            logger.info(f"✅ NAVEGACIÓN VERIFICADA a página {target_page} (URL directa)")
            return True, new_signature
        else:
            logger.warning(f"❌ Navegación FALLÓ - página no cambió (URL directa)")
            
    except Exception as e:
        logger.debug(f"Método 3 falló: {e}")
    
    logger.error(f"❌ TODOS los métodos de navegación FALLARON para página {target_page}")
    return False, current_signature

def scrape_all_pages_with_verification(driver):
    """Scraper con verificación REAL de navegación"""
    all_remates = []
    current_page = 1
    max_pages = 100
    failed_navigation_count = 0
    max_failed_navigation = 2
    
    logger.info(f"🚀 Iniciando scraping con verificación REAL de navegación")
    
    # Obtener signature de la primera página
    current_signature = get_page_signature(driver)
    logger.info(f"📄 Signature inicial de página 1: {current_signature}")
    
    while current_page <= max_pages:
        logger.info(f"📄 PROCESANDO PÁGINA {current_page} (Total remates: {len(all_remates)})")
        
        # Extraer remates de la página actual
        page_remates = extract_remates_clean(driver)
        
        if page_remates:
            failed_navigation_count = 0  # Reset
            
            # Verificar que no sean remates duplicados de página anterior
            if all_remates:
                # Comparar últimos números de remate
                last_numbers = {r['numero'] for r in all_remates[-4:]}  # Últimos 4
                current_numbers = {r['numero'] for r in page_remates}
                
                if last_numbers == current_numbers:
                    logger.error(f"🔄 PÁGINA DUPLICADA DETECTADA - Mismos remates que página anterior")
                    logger.error(f"   Números anteriores: {sorted(last_numbers)}")
                    logger.error(f"   Números actuales: {sorted(current_numbers)}")
                    break
            
            # Agregar metadata
            for idx, remate in enumerate(page_remates):
                remate['pagina'] = current_page
                remate['index_global'] = len(all_remates) + idx + 1
                remate['scraped_at'] = datetime.now().isoformat()
            
            all_remates.extend(page_remates)
            logger.info(f"✅ PÁGINA {current_page}: {len(page_remates)} remates ÚNICOS " +
                       f"(Total acumulado: {len(all_remates)})")
        else:
            logger.warning(f"❌ Página {current_page}: Sin datos")
        
        # Intentar navegar a siguiente página con verificación
        target_page = current_page + 1
        navigation_success, new_signature = navigate_and_verify(driver, current_page, target_page, current_signature)
        
        if navigation_success:
            current_signature = new_signature
            current_page = target_page
        else:
            failed_navigation_count += 1
            logger.error(f"💥 FALLÓ NAVEGACIÓN A PÁGINA {target_page} " +
                        f"(Fallos consecutivos: {failed_navigation_count})")
            
            if failed_navigation_count >= max_failed_navigation:
                logger.info(f"🏁 Máximo de fallos de navegación alcanzado. FINALIZANDO.")
                break
    
    return all_remates, current_page - 1

def scrape_remaju():
    """Función principal con verificación REAL de navegación"""
    driver = None
    url = "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml"
    
    try:
        logger.info("🚀 Iniciando scraping REMAJU con verificación REAL de navegación")
        
        driver = setup_driver()
        driver.set_page_load_timeout(30)
        
        logger.info(f"Navegando a: {url}")
        driver.get(url)
        time.sleep(8)
        
        page_title = driver.title
        logger.info(f"Título: {page_title}")
        
        # Scraping con verificación
        all_remates, total_pages = scrape_all_pages_with_verification(driver)
        
        # Estadísticas
        remates_con_precio = len([r for r in all_remates if r.get('precio_numerico', 0) > 0])
        remates_con_descripcion = len([r for r in all_remates if r.get('descripcion', '').strip()])
        
        # Resultado final
        resultado = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "url": url,
            "scraping_mode": "verified_navigation",
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
        
        logger.info(f"🎯 SCRAPING COMPLETADO:")
        logger.info(f"   📊 TOTAL REMATES: {len(all_remates)}")
        logger.info(f"   📄 PÁGINAS PROCESADAS: {total_pages}")
        logger.info(f"   💰 CON PRECIO: {remates_con_precio}")
        logger.info(f"   📝 CON DESCRIPCIÓN: {remates_con_descripcion}")
        logger.info(f"   📈 PROMEDIO POR PÁGINA: {round(len(all_remates) / total_pages if total_pages > 0 else 0, 1)}")
        
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
    print(f"RESULTADO FINAL: {result.get('status')}")
    if 'resumen' in result:
        print(f"🎯 TOTAL REMATES: {result['resumen']['total_remates']}")
        print(f"📄 PÁGINAS: {result['resumen']['paginas_procesadas']}")
        if result['resumen']['total_remates'] < 50:
            print("⚠️  ADVERTENCIA: Posible problema de navegación")
        else:
            print("✅ SCRAPING EXITOSO")
