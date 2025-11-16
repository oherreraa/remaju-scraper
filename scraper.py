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

def parse_precio_base(text_lines, start_index):
    """Extraer precio base y moneda"""
    precio_info = {
        "precio_base_texto": "",
        "moneda": "",
        "monto": "",
        "monto_numerico": 0
    }
    
    # Buscar líneas relacionadas con precio
    for i in range(start_index, min(start_index + 5, len(text_lines))):
        if i >= len(text_lines):
            break
            
        line = text_lines[i].strip()
        
        if "precio base" in line.lower():
            precio_info["precio_base_texto"] = line
            # La siguiente línea suele tener el monto
            if i + 1 < len(text_lines):
                next_line = text_lines[i + 1].strip()
                if "s/." in next_line.lower() or "$" in next_line:
                    precio_info["moneda"] = "PEN" if "s/." in next_line.lower() else "USD"
                    precio_info["monto"] = next_line
                    
                    # Extraer número
                    numbers = re.findall(r'[\d,]+\.?\d*', next_line.replace(',', ''))
                    if numbers:
                        try:
                            precio_info["monto_numerico"] = float(numbers[0])
                        except:
                            precio_info["monto_numerico"] = 0
        
        elif ("s/." in line.lower() or "$" in line) and any(char.isdigit() for char in line):
            if not precio_info["monto"]:
                precio_info["moneda"] = "PEN" if "s/." in line.lower() else "USD"
                precio_info["monto"] = line
                
                # Extraer número
                numbers = re.findall(r'[\d,]+\.?\d*', line.replace(',', ''))
                if numbers:
                    try:
                        precio_info["monto_numerico"] = float(numbers[0])
                    except:
                        precio_info["monto_numerico"] = 0
    
    return precio_info

def parse_fechas_y_estado(text_lines, start_index):
    """Extraer fechas, estado y fase"""
    fecha_info = {
        "fecha_limite": "",
        "hora_limite": "", 
        "estado_proceso": "",
        "fase_actual": "",
        "convocatoria": ""
    }
    
    for i in range(start_index, min(start_index + 10, len(text_lines))):
        if i >= len(text_lines):
            break
            
        line = text_lines[i].strip()
        
        # Detectar fechas (formato dd/mm/yyyy)
        if re.match(r'\d{2}/\d{2}/\d{4}', line):
            fecha_info["fecha_limite"] = line
        
        # Detectar horas (formato hh:mm AM/PM)
        elif re.match(r'\d{1,2}:\d{2}\s*(AM|PM)', line):
            fecha_info["hora_limite"] = line
        
        # Estados de proceso
        elif "presentación de ofertas" in line.lower():
            fecha_info["estado_proceso"] = line
        elif "en proceso" in line.lower():
            fecha_info["fase_actual"] = line
        elif "publicación e inscripcion" in line.lower():
            fecha_info["fase_actual"] = line
        elif "convocatoria" in line.lower():
            fecha_info["convocatoria"] = line
    
    return fecha_info

def extract_detailed_remates(driver):
    """Extraer remates con TODOS los detalles"""
    try:
        # Obtener todo el texto de la página
        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        
        remates = []
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Detectar inicio de remate
            if "remate n°" in line.lower() and "convocatoria" in line.lower():
                logger.info(f"Procesando: {line}")
                
                # Inicializar remate con estructura completa
                remate = {
                    # Información básica
                    "numero_remate": line,
                    "numero_remate_limpio": "",
                    "tipo_convocatoria": "",
                    "numero_convocatoria": "",
                    
                    # Tipo y clasificación
                    "tipo_remate": "",
                    "clasificacion": "",
                    
                    # Ubicación
                    "ubicacion_distrito": "",
                    "ubicacion_provincia": "", 
                    "ubicacion_departamento": "",
                    "ubicacion_completa": "",
                    
                    # Fechas y estado
                    "fecha_limite": "",
                    "hora_limite": "",
                    "estado_proceso": "",
                    "fase_actual": "",
                    "situacion": "",
                    
                    # Descripción del bien
                    "descripcion_bien": "",
                    "descripcion_completa": "",
                    "tipo_inmueble": "",
                    "area_terreno": "",
                    "direccion_especifica": "",
                    
                    # Precio
                    "precio_base_texto": "",
                    "moneda": "",
                    "monto": "",
                    "monto_numerico": 0,
                    
                    # Información adicional
                    "partida_registral": "",
                    "zona_registral": "",
                    "inscripcion_registral": "",
                    
                    # Enlaces y seguimiento
                    "tiene_seguimiento": False,
                    "tiene_detalle": False,
                    "tiene_aviso": False,
                    
                    # Metadatos
                    "texto_completo": "",
                    "lineas_raw": []
                }
                
                # Extraer número de remate limpio
                numero_match = re.search(r'remate n°?\s*(\d+)', line.lower())
                if numero_match:
                    remate["numero_remate_limpio"] = numero_match.group(1)
                
                # Extraer tipo de convocatoria
                if "primera convocatoria" in line.lower():
                    remate["tipo_convocatoria"] = "PRIMERA CONVOCATORIA"
                elif "segunda convocatoria" in line.lower():
                    remate["tipo_convocatoria"] = "SEGUNDA CONVOCATORIA"
                
                # Recopilar las siguientes líneas para este remate
                remate_lines = []
                j = i + 1
                
                # Recopilar hasta encontrar el siguiente remate o llegar al final
                while j < len(lines):
                    next_line = lines[j].strip()
                    
                    # Si encontramos otro remate, parar
                    if "remate n°" in next_line.lower() and "convocatoria" in next_line.lower():
                        break
                    
                    # Si encontramos indicadores de fin de remate
                    if next_line.lower() in ["seguimiento", "detalle", "aviso"] and j + 1 < len(lines):
                        # Estas son las últimas líneas del remate
                        remate_lines.append(next_line)
                        
                        # Marcar que tiene estos elementos
                        if "seguimiento" in next_line.lower():
                            remate["tiene_seguimiento"] = True
                        if "detalle" in next_line.lower():
                            remate["tiene_detalle"] = True
                        if "aviso" in next_line.lower():
                            remate["tiene_aviso"] = True
                        
                        # Saltar estas líneas finales
                        while j + 1 < len(lines) and lines[j + 1].strip().lower() in ["seguimiento", "detalle", "aviso"]:
                            j += 1
                            if j < len(lines):
                                final_line = lines[j].strip()
                                if final_line.lower() in ["seguimiento", "detalle", "aviso"]:
                                    if "seguimiento" in final_line.lower():
                                        remate["tiene_seguimiento"] = True
                                    if "detalle" in final_line.lower():
                                        remate["tiene_detalle"] = True
                                    if "aviso" in final_line.lower():
                                        remate["tiene_aviso"] = True
                        break
                    
                    remate_lines.append(next_line)
                    j += 1
                
                # Guardar líneas raw
                remate["lineas_raw"] = remate_lines
                remate["texto_completo"] = "\n".join([line] + remate_lines)
                
                # Procesar líneas para extraer detalles
                for idx, rline in enumerate(remate_lines):
                    rline = rline.strip()
                    
                    # Tipo de remate (primera línea después del número)
                    if idx == 0 and ("remate" in rline.lower() or "simple" in rline.lower()):
                        remate["tipo_remate"] = rline
                    
                    # Ubicación (segunda línea generalmente)
                    elif idx == 1 and len(rline) > 3 and rline.isupper():
                        remate["ubicacion_distrito"] = rline
                        remate["ubicacion_completa"] = rline
                    
                    # Estados y fechas
                    elif "presentación de ofertas" in rline.lower():
                        remate["estado_proceso"] = rline
                    elif re.match(r'\d{2}/\d{2}/\d{4}', rline):
                        remate["fecha_limite"] = rline
                    elif re.match(r'\d{1,2}:\d{2}\s*(AM|PM)', rline):
                        remate["hora_limite"] = rline
                    elif "en proceso" in rline.lower():
                        remate["situacion"] = rline
                    elif "publicación e inscripcion" in rline.lower():
                        remate["fase_actual"] = rline
                    
                    # Descripción del bien (líneas largas)
                    elif len(rline) > 50 and not any(keyword in rline.lower() for keyword in 
                                                   ['precio', 'seguimiento', 'detalle', 'aviso', 'remate']):
                        if not remate["descripcion_bien"]:
                            remate["descripcion_bien"] = rline
                            remate["descripcion_completa"] = rline
                            
                            # Extraer detalles específicos de la descripción
                            if "área de" in rline.lower():
                                area_match = re.search(r'área de ([\d,\.]+\s*m2?)', rline.lower())
                                if area_match:
                                    remate["area_terreno"] = area_match.group(1)
                            
                            # Extraer tipo de inmueble de la descripción
                            tipos_inmueble = ['casa', 'departamento', 'terreno', 'local', 'oficina', 'estacionamiento']
                            for tipo in tipos_inmueble:
                                if tipo in rline.lower():
                                    remate["tipo_inmueble"] = tipo.upper()
                                    break
                            
                            # Extraer información registral
                            if "partida" in rline.lower():
                                partida_match = re.search(r'partida.*?n[°º]?\s*([\d\-]+)', rline.lower())
                                if partida_match:
                                    remate["partida_registral"] = partida_match.group(1)
                            
                            if "zona registral" in rline.lower():
                                zona_match = re.search(r'zona registral.*?n[°º]?\s*([\w\s]+?)(?:\s*–|\s*-|$)', rline.lower())
                                if zona_match:
                                    remate["zona_registral"] = zona_match.group(1).strip()
                
                # Extraer información de precio
                precio_info = parse_precio_base(remate_lines, 0)
                remate.update(precio_info)
                
                # Extraer fechas y estado adicional
                fecha_info = parse_fechas_y_estado(remate_lines, 0)
                remate.update(fecha_info)
                
                # Solo agregar si tiene información sustancial
                if (remate["numero_remate_limpio"] and 
                    (remate["descripcion_bien"] or remate["ubicacion_distrito"] or remate["monto"])):
                    
                    remates.append(remate)
                    logger.info(f"✅ Remate agregado: {remate['numero_remate_limpio']} - {remate['ubicacion_distrito']}")
                else:
                    logger.warning(f"⚠️ Remate descartado por falta de datos: {line}")
                
                # Continuar desde donde terminamos
                i = j
            else:
                i += 1
        
        logger.info(f"Total remates procesados: {len(remates)}")
        return remates
        
    except Exception as e:
        logger.error(f"Error en extract_detailed_remates: {e}")
        return []

def scrape_limited_pages(driver, max_pages=10):
    """Scraper con detalles completos"""
    all_remates = []
    current_page = 1
    
    while current_page <= max_pages:
        logger.info(f"📄 Página {current_page}/{max_pages}")
        
        # Esperar carga
        time.sleep(3)
        
        # Extraer datos detallados
        page_remates = extract_detailed_remates(driver)
        
        if page_remates:
            for idx, remate in enumerate(page_remates):
                remate['pagina'] = current_page
                remate['index_en_pagina'] = idx + 1
                remate['index_global'] = len(all_remates) + idx + 1
                remate['scraped_at'] = datetime.now().isoformat()
            
            all_remates.extend(page_remates)
            logger.info(f"✅ Página {current_page}: {len(page_remates)} remates detallados")
        else:
            logger.warning(f"❌ Página {current_page}: Sin datos")
        
        # Navegación a siguiente página
        try:
            next_found = False
            
            # Método 1: Buscar número específico de página
            for page_num in range(current_page + 1, current_page + 3):
                try:
                    next_link = driver.find_element(By.XPATH, f"//a[text()='{page_num}']")
                    if next_link.is_displayed() and next_link.is_enabled():
                        logger.info(f"🔄 Navegando a página {page_num}")
                        next_link.click()
                        next_found = True
                        break
                except:
                    continue
            
            # Método 2: Buscar botón "N" (Next)
            if not next_found:
                try:
                    next_btn = driver.find_element(By.XPATH, "//a[text()='N']")
                    if next_btn.is_displayed() and next_btn.is_enabled():
                        logger.info("🔄 Navegando con botón N")
                        next_btn.click()
                        next_found = True
                except:
                    pass
            
            if not next_found:
                logger.info("🏁 No hay más páginas disponibles")
                break
                
            current_page += 1
            time.sleep(4)  # Esperar carga de nueva página
            
        except Exception as e:
            logger.error(f"Error navegando: {e}")
            break
    
    return all_remates, current_page - 1

def scrape_remaju():
    """Función principal con detalles completos"""
    driver = None
    url = "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml"
    
    try:
        max_pages = int(os.getenv('MAX_PAGES', '10'))
        logger.info(f"🚀 Iniciando scraping detallado - máximo {max_pages} páginas")
        
        driver = setup_driver()
        driver.set_page_load_timeout(30)
        
        logger.info(f"Navegando a: {url}")
        driver.get(url)
        time.sleep(6)
        
        page_title = driver.title
        logger.info(f"Título: {page_title}")
        
        # Scraping con detalles completos
        all_remates, total_pages = scrape_limited_pages(driver, max_pages)
        
        # Estadísticas adicionales
        remates_con_precio = len([r for r in all_remates if r.get('monto_numerico', 0) > 0])
        remates_con_descripcion = len([r for r in all_remates if r.get('descripcion_bien')])
        
        # Crear resultado final
        resultado = {
            "status": "success" if all_remates else "partial_success",
            "timestamp": datetime.now().isoformat(),
            "url_scraped": url,
            "scraping_mode": "detailed_extraction",
            "max_pages_configured": max_pages,
            "total_pages_scraped": total_pages,
            "estadisticas": {
                "total_remates": len(all_remates),
                "remates_con_precio": remates_con_precio,
                "remates_con_descripcion": remates_con_descripcion,
                "porcentaje_completitud_precio": round((remates_con_precio/len(all_remates)*100) if all_remates else 0, 2),
                "porcentaje_completitud_descripcion": round((remates_con_descripcion/len(all_remates)*100) if all_remates else 0, 2)
            },
            "estructura_campos": {
                "basicos": ["numero_remate", "tipo_remate", "ubicacion_distrito"],
                "fechas": ["fecha_limite", "hora_limite", "estado_proceso", "fase_actual"], 
                "ubicacion": ["ubicacion_distrito", "ubicacion_provincia", "ubicacion_departamento", "direccion_especifica"],
                "descripcion": ["descripcion_bien", "tipo_inmueble", "area_terreno"],
                "precio": ["precio_base_texto", "moneda", "monto", "monto_numerico"],
                "registral": ["partida_registral", "zona_registral"],
                "metadatos": ["pagina", "index_global", "scraped_at"]
            },
            "remates": all_remates
        }
        
        # Guardar resultado
        output_file = "remates_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        # Crear backup
        backup_file = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Completado: {len(all_remates)} remates con detalles completos")
        logger.info(f"📊 Estadísticas: {remates_con_precio} con precio, {remates_con_descripcion} con descripción")
        logger.info(f"📁 Archivos: {output_file}, {backup_file}")
        
        # Outputs para GitHub Actions
        print(f"total_remates={len(all_remates)}")
        print(f"remates_con_precio={remates_con_precio}")
        print(f"status=success")
        
        return resultado
        
    except Exception as e:
        error_result = {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "url": url
        }
        
        error_file = "remates_result.json"
        with open(error_file, 'w', encoding='utf-8') as f:
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
    print(f"Resultado: {result.get('status', 'unknown')}")
    print(f"Total remates: {result.get('estadisticas', {}).get('total_remates', 0)}")
    print(f"Con precio: {result.get('estadisticas', {}).get('remates_con_precio', 0)}")
    print(f"Con descripción: {result.get('estadisticas', {}).get('remates_con_descripcion', 0)}")
