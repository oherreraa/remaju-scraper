import json
import os
import time
import logging
import random
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_driver():
    """Configurar Chrome driver para evadir detección de bots"""
    chrome_options = Options()
    
    # Opciones básicas para GitHub Actions
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    
    # Opciones anti-detección
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--start-maximized')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Headers más realistas
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ]
    
    chrome_options.add_argument(f'--user-agent={random.choice(user_agents)}')
    
    # Configurar driver
    if os.getenv('GITHUB_ACTIONS'):
        logger.info("Ejecutando en GitHub Actions")
        driver = webdriver.Chrome(options=chrome_options)
    else:
        logger.info("Ejecutando localmente")
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            driver = webdriver.Chrome(ChromeDriverManager().install(), options=chrome_options)
        except:
            driver = webdriver.Chrome(options=chrome_options)
    
    # Script para evadir detección
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def human_like_delay(min_delay=2, max_delay=4):
    """Delay aleatorio para simular comportamiento humano"""
    time.sleep(random.uniform(min_delay, max_delay))

def extract_remate_data(driver):
    """Extraer datos de remates de la página actual usando estructura real"""
    page_remates = []
    
    try:
        # Buscar elementos que contengan información de remates
        # Basado en el HTML real, los remates están en divs con texto específico
        
        # Primero, buscar todos los elementos que contengan "Remate N°"
        remate_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Remate N°')]")
        logger.info(f"Elementos con 'Remate N°' encontrados: {len(remate_elements)}")
        
        if not remate_elements:
            # Buscar de otra forma - cualquier elemento con números de remate
            remate_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'N°') and contains(text(), 'CONVOCATORIA')]")
            logger.info(f"Elementos con patrón de convocatoria: {len(remate_elements)}")
        
        # Para cada elemento de remate encontrado, extraer información del contexto
        for i, element in enumerate(remate_elements):
            try:
                # Obtener el contenedor padre que tiene toda la información del remate
                parent_container = element
                
                # Buscar el contenedor más amplio que contenga toda la info del remate
                for _ in range(5):  # Buscar hasta 5 niveles arriba
                    try:
                        parent_container = parent_container.find_element(By.XPATH, "..")
                        parent_text = parent_container.text
                        
                        # Si encontramos un contenedor con precio base, es el correcto
                        if "Precio Base" in parent_text:
                            break
                    except:
                        break
                
                # Extraer texto completo del contenedor
                full_text = parent_container.text
                lines = [line.strip() for line in full_text.split('\n') if line.strip()]
                
                # Parsear información específica
                remate_data = {
                    "numero_remate": "",
                    "convocatoria": "",
                    "tipo_remate": "",
                    "ubicacion": "",
                    "estado": "",
                    "fecha_limite": "",
                    "hora_limite": "",
                    "fase": "",
                    "descripcion_bien": "",
                    "precio_base": "",
                    "moneda": "",
                    "texto_completo": full_text,
                    "lineas_parseadas": lines
                }
                
                # Extraer datos específicos línea por línea
                for j, line in enumerate(lines):
                    line_lower = line.lower()
                    
                    if "remate n°" in line_lower:
                        remate_data["numero_remate"] = line
                        # La siguiente línea suele ser el tipo de remate
                        if j + 1 < len(lines):
                            remate_data["tipo_remate"] = lines[j + 1]
                        # La línea después suele ser la ubicación
                        if j + 2 < len(lines):
                            remate_data["ubicacion"] = lines[j + 2]
                    
                    elif "presentación de ofertas" in line_lower:
                        remate_data["estado"] = line
                    
                    elif any(month in line for month in ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]) and "/" in line:
                        if ":" not in line:  # Es fecha, no hora
                            remate_data["fecha_limite"] = line
                        else:  # Es hora
                            remate_data["hora_limite"] = line
                    
                    elif "precio base" in line_lower:
                        remate_data["precio_base"] = line
                        # La siguiente línea suele tener la moneda y monto
                        if j + 1 < len(lines):
                            next_line = lines[j + 1]
                            if "s/." in next_line or "$" in next_line:
                                remate_data["moneda"] = "PEN" if "s/." in next_line else "USD"
                                remate_data["precio_base"] = next_line
                    
                    elif len(line) > 50 and not any(keyword in line_lower for keyword in ["remate", "precio", "seguimiento", "detalle", "aviso"]):
                        # Línea larga sin palabras clave, probablemente descripción del bien
                        if not remate_data["descripcion_bien"]:
                            remate_data["descripcion_bien"] = line
                
                # Solo agregar si tiene información sustancial
                if remate_data["numero_remate"] and any(remate_data[key] for key in ["ubicacion", "precio_base", "descripcion_bien"]):
                    remate_data["index_en_pagina"] = i + 1
                    remate_data["scraped_at"] = datetime.now().isoformat()
                    page_remates.append(remate_data)
                    
            except Exception as e:
                logger.warning(f"Error procesando remate {i}: {e}")
                continue
        
        # Si no encontramos remates con el método anterior, usar método alternativo
        if not page_remates:
            logger.info("Método alternativo: buscando por precio base...")
            
            # Buscar elementos que contengan "Precio Base"
            precio_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Precio Base')]")
            
            for i, element in enumerate(precio_elements):
                try:
                    # Obtener el contenedor padre
                    parent = element.find_element(By.XPATH, "../..")
                    text = parent.text
                    
                    if "Remate N°" in text:
                        simple_remate = {
                            "numero_remate": f"Remate_encontrado_{i+1}",
                            "texto_completo": text,
                            "metodo_extraccion": "precio_base_search",
                            "index_en_pagina": i + 1,
                            "scraped_at": datetime.now().isoformat()
                        }
                        page_remates.append(simple_remate)
                        
                except Exception as e:
                    continue
        
        logger.info(f"✅ Remates extraídos de la página: {len(page_remates)}")
        return page_remates
        
    except Exception as e:
        logger.error(f"❌ Error en extract_remate_data: {e}")
        return []

def change_rows_per_page(driver, rows=12):
    """Cambiar a mostrar más filas por página"""
    try:
        logger.info(f"Intentando cambiar a {rows} filas por página...")
        
        # Buscar el control "Rows Per Page"
        rows_selectors = [
            f"//select[contains(@class, 'rows')]/option[@value='{rows}']",
            f"//select/option[text()='{rows}']",
            f"//option[@value='{rows}']",
            f"//*[text()='{rows}' and contains(@onclick, 'rows')]"
        ]
        
        for selector in rows_selectors:
            try:
                element = driver.find_element(By.XPATH, selector)
                if element.is_displayed():
                    element.click()
                    logger.info(f"✅ Cambiado a {rows} filas por página")
                    human_like_delay(3, 5)  # Esperar que recargue
                    return True
            except:
                continue
                
        logger.warning(f"No se pudo cambiar a {rows} filas por página")
        return False
        
    except Exception as e:
        logger.warning(f"Error cambiando filas por página: {e}")
        return False

def find_next_page_button(driver):
    """Encontrar botón de página siguiente"""
    try:
        # Basado en el HTML real, buscar botones de paginación
        next_selectors = [
            "//a[text()='N']",  # Botón "N" (Next) visible en el HTML
            "//a[contains(@onclick, 'next')]",
            "//a[text()='>']",
            "//a[text()='»']",
            "//*[@title='Next Page']",
            "//*[@title='Siguiente']"
        ]
        
        for selector in next_selectors:
            try:
                element = driver.find_element(By.XPATH, selector)
                if element.is_displayed() and element.is_enabled():
                    # Verificar que no esté deshabilitado
                    classes = element.get_attribute('class') or ''
                    if 'disabled' not in classes.lower():
                        return element
            except:
                continue
                
        # Buscar por números de página (2, 3, 4, etc.)
        current_page_info = driver.page_source
        
        # Extraer número de página actual y buscar siguiente
        for page_num in range(2, 70):  # Buscar hasta página 70
            try:
                page_link = driver.find_element(By.XPATH, f"//a[text()='{page_num}']")
                if page_link.is_displayed() and page_link.is_enabled():
                    return page_link
            except:
                continue
                
        return None
        
    except Exception as e:
        logger.warning(f"Error buscando botón siguiente: {e}")
        return None

def scrape_with_pagination(driver):
    """Scraper principal con paginación para REMAJU"""
    all_remates = []
    current_page = 1
    max_pages = 70  # Basado en 267 registros / ~4 por página
    
    # Primero intentar cambiar a más registros por página
    change_rows_per_page(driver, 12)
    
    while current_page <= max_pages:
        logger.info(f"📄 Scrapeando página {current_page}...")
        
        # Esperar que cargue el contenido
        human_like_delay(3, 5)
        
        # Extraer datos de la página actual
        page_data = extract_remate_data(driver)
        
        if page_data:
            logger.info(f"✅ Página {current_page}: {len(page_data)} remates encontrados")
            
            # Agregar metadata a cada remate
            for i, remate in enumerate(page_data):
                remate['pagina'] = current_page
                remate['index_global'] = len(all_remates) + i + 1
            
            all_remates.extend(page_data)
        else:
            logger.warning(f"❌ Página {current_page}: No se encontraron datos")
            
            # Si no hay datos en 2 páginas consecutivas, probablemente terminamos
            if current_page > 1:
                logger.info("No hay más datos. Finalizando scraping.")
                break
        
        # Buscar botón siguiente
        next_button = find_next_page_button(driver)
        
        if next_button:
            try:
                logger.info(f"🔄 Navegando a página {current_page + 1}...")
                
                # Scroll hasta el botón
                driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                human_like_delay(1, 2)
                
                # Clic en el botón
                try:
                    next_button.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", next_button)
                
                # Esperar que cambie la página
                human_like_delay(5, 7)
                current_page += 1
                
            except Exception as e:
                logger.error(f"❌ Error navegando: {e}")
                break
        else:
            logger.info("🏁 No se encontró botón siguiente. Fin de paginación.")
            break
    
    return all_remates, current_page - 1

def scrape_remaju():
    """Función principal de scraping REMAJU"""
    driver = None
    url = "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml"
    
    try:
        logger.info("🚀 Iniciando scraping de REMAJU (estructura real)...")
        driver = setup_driver()
        
        logger.info(f"Navegando a: {url}")
        driver.get(url)
        
        # Esperar carga inicial
        logger.info("Esperando carga inicial...")
        human_like_delay(5, 8)
        
        # Verificar título
        page_title = driver.title
        logger.info(f"Título: {page_title}")
        
        # Realizar scraping con paginación
        all_remates, total_pages = scrape_with_pagination(driver)
        
        # Crear resultado
        resultado = {
            "status": "success" if all_remates else "success_no_data",
            "timestamp": datetime.now().isoformat(),
            "url_scraped": url,
            "page_title": page_title,
            "total_remates": len(all_remates),
            "total_pages_scraped": total_pages,
            "remates": all_remates
        }
        
        # Guardar resultado
        output_file = "remates_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Scraping completado: {len(all_remates)} remates, {total_pages} páginas")
        
        # Outputs para GitHub Actions
        print(f"total_remates={len(all_remates)}")
        print(f"total_pages={total_pages}")
        print(f"status=success")
        
        return resultado
        
    except Exception as e:
        error_result = {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_message": str(e),
            "error_type": type(e).__name__,
            "url_attempted": url
        }
        
        logger.error(f"❌ Error: {e}")
        
        with open('remates_result.json', 'w', encoding='utf-8') as f:
            json.dump(error_result, f, ensure_ascii=False, indent=2)
        
        print(f"status=error")
        return error_result
        
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    result = scrape_remaju()
    print("=" * 60)
    print("RESULTADO FINAL:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
