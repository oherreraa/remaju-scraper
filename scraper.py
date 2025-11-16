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

def extract_page_data(driver):
    """Extraer datos de la página actual"""
    page_remates = []
    
    # Selectors específicos para REMAJU
    selectors_to_try = [
        "table[id*='remate'] tbody tr",
        "table[id*='tabla'] tbody tr", 
        "table[id*='grid'] tbody tr",
        ".rich-table tbody tr",
        ".rf-dt-r",  # RichFaces DataTable Row
        "tbody tr",
        "table tr"
    ]
    
    all_rows = []
    for selector in selectors_to_try:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                logger.info(f"Encontrados {len(elements)} elementos con: {selector}")
                all_rows = elements
                break
        except Exception:
            continue
    
    # Procesar filas encontradas
    for i, row in enumerate(all_rows):
        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            if not cells:
                cells = row.find_elements(By.TAG_NAME, "th")
            
            if len(cells) >= 2:
                cell_texts = [cell.text.strip() for cell in cells]
                
                # Filtrar filas válidas
                if any(text and len(text) > 2 for text in cell_texts):
                    # Verificar que no sea encabezado
                    row_text = " ".join(cell_texts).lower()
                    if not any(header_word in row_text for header_word in 
                             ['expediente', 'demandado', 'bien', 'ubicacion', 'fecha', 'valor']):
                        
                        remate = {
                            "expediente": cell_texts[0] if len(cell_texts) > 0 else "",
                            "demandado": cell_texts[1] if len(cell_texts) > 1 else "",
                            "bien": cell_texts[2] if len(cell_texts) > 2 else "",
                            "ubicacion": cell_texts[3] if len(cell_texts) > 3 else "",
                            "fecha_remate": cell_texts[4] if len(cell_texts) > 4 else "",
                            "valor_base": cell_texts[5] if len(cell_texts) > 5 else "",
                            "datos_completos": cell_texts,
                            "total_columns": len(cell_texts)
                        }
                        
                        # Solo agregar si tiene datos sustanciales
                        if any(len(str(remate[key])) > 3 for key in ['expediente', 'demandado', 'bien']):
                            page_remates.append(remate)
                    
        except Exception as e:
            logger.warning(f"Error procesando fila {i}: {e}")
            continue
    
    return page_remates

def find_next_button(driver):
    """Encontrar el botón 'Siguiente' para paginación"""
    
    # Posibles selectores para botón siguiente
    next_selectors = [
        # JSF/PrimeFaces típicos
        "a[title*='next']",
        "a[title*='siguiente']", 
        "a[title*='Next']",
        "a[title*='Siguiente']",
        "button[title*='next']",
        "button[title*='siguiente']",
        
        # Por texto
        "//a[contains(text(), 'Siguiente')]",
        "//a[contains(text(), 'Next')]", 
        "//a[contains(text(), '»')]",
        "//a[contains(text(), '>')]",
        "//button[contains(text(), 'Siguiente')]",
        "//button[contains(text(), 'Next')]",
        
        # Por clases comunes
        ".pagination a[rel='next']",
        ".pagination .next",
        ".pager .next",
        ".dataTables_paginate .next",
        
        # JSF específicos
        ".rich-datascroller-button[title*='next']",
        ".rf-ds-btn[title*='next']",
        
        # Por ID comunes
        "#nextPage",
        "#next",
        
        # Selectores genéricos (últimos)
        "a[onclick*='next']",
        "a[href*='next']"
    ]
    
    for selector in next_selectors:
        try:
            if selector.startswith('//'):
                # XPath selector
                elements = driver.find_elements(By.XPATH, selector)
            else:
                # CSS selector
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                
            for element in elements:
                # Verificar si el elemento está visible y habilitado
                if element.is_displayed() and element.is_enabled():
                    # Verificar que no esté disabled
                    class_name = element.get_attribute('class') or ''
                    if 'disabled' not in class_name.lower():
                        logger.info(f"Botón siguiente encontrado con selector: {selector}")
                        return element
                        
        except Exception as e:
            continue
    
    return None

def scrape_with_pagination(driver):
    """Scraper principal con manejo de paginación"""
    all_remates = []
    current_page = 1
    max_pages = 50  # Límite de seguridad para evitar loops infinitos
    
    while current_page <= max_pages:
        logger.info(f"📄 Scrapeando página {current_page}...")
        
        # Esperar que cargue el contenido
        human_like_delay(3, 5)
        
        # Extraer datos de la página actual
        page_data = extract_page_data(driver)
        
        if page_data:
            logger.info(f"✅ Página {current_page}: {len(page_data)} remates encontrados")
            
            # Agregar número de página a cada remate
            for i, remate in enumerate(page_data):
                remate['pagina'] = current_page
                remate['index_global'] = len(all_remates) + i + 1
                remate['scraped_at'] = datetime.now().isoformat()
            
            all_remates.extend(page_data)
        else:
            logger.warning(f"❌ Página {current_page}: No se encontraron datos")
        
        # Buscar botón "Siguiente"
        next_button = find_next_button(driver)
        
        if next_button:
            try:
                logger.info(f"🔄 Navegando a página {current_page + 1}...")
                
                # Scroll hasta el botón si es necesario
                driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                human_like_delay(1, 2)
                
                # Intentar clic normal primero
                try:
                    next_button.click()
                except ElementClickInterceptedException:
                    # Si falla, usar JavaScript
                    driver.execute_script("arguments[0].click();", next_button)
                
                # Esperar que cambie la página
                human_like_delay(3, 5)
                
                # Verificar si realmente cambió la página
                new_page_data = extract_page_data(driver)
                
                # Si los datos son exactamente iguales, probablemente llegamos al final
                if page_data and new_page_data and page_data == new_page_data:
                    logger.info("🏁 Los datos son iguales a la página anterior. Fin de paginación.")
                    break
                
                current_page += 1
                
            except Exception as e:
                logger.error(f"❌ Error navegando a siguiente página: {e}")
                break
        else:
            logger.info("🏁 No se encontró botón 'Siguiente'. Fin de paginación.")
            break
    
    return all_remates, current_page - 1

def scrape_remaju():
    """Función principal de scraping con paginación completa"""
    driver = None
    url = "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml"
    
    try:
        logger.info("🚀 Iniciando scraping de REMAJU con paginación...")
        driver = setup_driver()
        
        logger.info(f"Navegando a: {url}")
        driver.get(url)
        
        # Delay inicial más largo
        logger.info("Esperando carga inicial...")
        human_like_delay(5, 8)
        
        # Verificar título de la página
        page_title = driver.title
        logger.info(f"Título de la página: {page_title}")
        
        if any(word in page_title.lower() for word in ['captcha', 'bot', 'blocked', 'radware']):
            logger.warning("⚠️ Posible detección de bot")
            
            # Comportamiento humano básico
            actions = ActionChains(driver)
            actions.move_by_offset(100, 100).perform()
            human_like_delay()
            
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            human_like_delay()
            driver.execute_script("window.scrollTo(0, 0);")
            human_like_delay()
            
            driver.refresh()
            human_like_delay(5, 8)
        
        # Realizar scraping con paginación
        all_remates, total_pages = scrape_with_pagination(driver)
        
        # Crear resultado final
        resultado = {
            "status": "success" if all_remates else "success_no_data",
            "timestamp": datetime.now().isoformat(),
            "url_scraped": url,
            "pagination_info": {
                "total_pages_scraped": total_pages,
                "has_pagination": total_pages > 1
            },
            "page_title": page_title,
            "bot_detection": any(word in page_title.lower() for word in ['captcha', 'bot', 'blocked']),
            "total_remates": len(all_remates),
            "summary_by_page": {},
            "remates": all_remates
        }
        
        # Crear resumen por página
        for page_num in range(1, total_pages + 1):
            page_remates = [r for r in all_remates if r.get('pagina') == page_num]
            resultado["summary_by_page"][f"page_{page_num}"] = len(page_remates)
        
        # Guardar resultado
        output_file = "remates_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Scraping completado:")
        logger.info(f"   📊 Total remates: {len(all_remates)}")
        logger.info(f"   📄 Páginas procesadas: {total_pages}")
        logger.info(f"   📁 Archivo guardado: {output_file}")
        
        # Outputs para GitHub Actions
        print(f"total_remates={len(all_remates)}")
        print(f"total_pages={total_pages}")
        print(f"status={'success' if all_remates else 'success_no_data'}")
        print(f"bot_detected={'yes' if resultado['bot_detection'] else 'no'}")
        
        return resultado
        
    except Exception as e:
        error_result = {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error_message": str(e),
            "error_type": type(e).__name__,
            "url_attempted": url
        }
        
        logger.error(f"❌ Error en scraping: {e}")
        
        with open('remates_result.json', 'w', encoding='utf-8') as f:
            json.dump(error_result, f, ensure_ascii=False, indent=2)
        
        print(f"status=error")
        print(f"error={str(e)}")
        
        return error_result
        
    finally:
        if driver:
            driver.quit()
            logger.info("🔒 Driver cerrado correctamente")

if __name__ == "__main__":
    result = scrape_remaju()
    print("=" * 60)
    print("RESULTADO FINAL:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
