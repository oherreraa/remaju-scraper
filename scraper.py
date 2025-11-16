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

def human_like_delay():
    """Delay aleatorio para simular comportamiento humano"""
    time.sleep(random.uniform(2, 5))

def scrape_remaju():
    """Función principal de scraping con evasión anti-bot"""
    driver = None
    url = "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml"
    
    try:
        logger.info("🚀 Iniciando scraping de REMAJU...")
        driver = setup_driver()
        
        logger.info(f"Navegando a: {url}")
        driver.get(url)
        
        # Delay inicial más largo
        logger.info("Esperando carga inicial...")
        human_like_delay()
        
        # Verificar si hay captcha o bloqueo
        page_title = driver.title.lower()
        logger.info(f"Título de la página: {driver.title}")
        
        if any(word in page_title for word in ['captcha', 'bot', 'blocked', 'radware']):
            logger.warning("⚠️ Posible detección de bot detectada")
            
            # Intentar comportamiento humano
            actions = ActionChains(driver)
            actions.move_by_offset(100, 100).perform()
            human_like_delay()
            
            # Scroll para simular lectura
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            human_like_delay()
            driver.execute_script("window.scrollTo(0, 0);")
            human_like_delay()
            
            # Refresh de la página
            logger.info("Intentando refresh de la página...")
            driver.refresh()
            human_like_delay()
        
        # Esperar más tiempo para el contenido dinámico
        logger.info("Esperando contenido dinámico...")
        time.sleep(10)
        
        # Obtener información de debug
        page_source_length = len(driver.page_source)
        current_title = driver.title
        logger.info(f"Título actual: {current_title}")
        logger.info(f"Longitud del HTML: {page_source_length}")
        
        # Buscar elementos de diferentes maneras
        logger.info("Buscando elementos de tabla...")
        
        # Esperar elementos específicos de REMAJU
        wait = WebDriverWait(driver, 20)
        
        # Posibles selectores específicos para sitios JSF
        selectors_to_try = [
            "table[id*='remate'] tbody tr",
            "table[id*='tabla'] tbody tr", 
            "table[id*='grid'] tbody tr",
            ".rich-table tbody tr",
            ".rf-dt-r",  # RichFaces DataTable Row
            "tbody tr",
            "table tr",
            "tr"
        ]
        
        all_rows = []
        for selector in selectors_to_try:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    logger.info(f"Encontrados {len(elements)} elementos con: {selector}")
                    all_rows.extend(elements)
            except Exception as e:
                continue
        
        # Remover duplicados manteniendo orden
        seen = set()
        unique_rows = []
        for row in all_rows:
            row_text = row.text.strip()
            if row_text and row_text not in seen and len(row_text) > 5:
                seen.add(row_text)
                unique_rows.append(row)
        
        logger.info(f"Filas únicas encontradas: {len(unique_rows)}")
        
        # Procesar datos
        remates = []
        for i, row in enumerate(unique_rows):
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                if not cells:
                    cells = row.find_elements(By.TAG_NAME, "th")
                
                if len(cells) >= 2:
                    cell_texts = [cell.text.strip() for cell in cells]
                    
                    # Filtrar filas de encabezado y vacías
                    if any(text and len(text) > 2 for text in cell_texts):
                        # Verificar que no sea encabezado
                        row_text = " ".join(cell_texts).lower()
                        if not any(header_word in row_text for header_word in 
                                 ['expediente', 'demandado', 'bien', 'ubicacion', 'fecha', 'valor']):
                            
                            remate = {
                                "index": len(remates) + 1,
                                "expediente": cell_texts[0] if len(cell_texts) > 0 else "",
                                "demandado": cell_texts[1] if len(cell_texts) > 1 else "",
                                "bien": cell_texts[2] if len(cell_texts) > 2 else "",
                                "ubicacion": cell_texts[3] if len(cell_texts) > 3 else "",
                                "fecha_remate": cell_texts[4] if len(cell_texts) > 4 else "",
                                "valor_base": cell_texts[5] if len(cell_texts) > 5 else "",
                                "datos_completos": cell_texts,
                                "total_columns": len(cell_texts),
                                "scraped_at": datetime.now().isoformat()
                            }
                            remates.append(remate)
                        
            except Exception as e:
                logger.warning(f"Error procesando fila {i}: {e}")
                continue
        
        # También buscar texto plano si no hay tablas
        if not remates:
            logger.info("No se encontraron datos en tablas, buscando texto plano...")
            body_text = driver.find_element(By.TAG_NAME, "body").text
            
            # Buscar patrones de remates en texto
            lines = body_text.split('\n')
            text_remates = []
            for line in lines:
                line = line.strip()
                if len(line) > 20 and any(keyword in line.lower() for keyword in 
                                        ['exp', 'expediente', 'remate', 'judicial']):
                    text_remates.append({
                        "index": len(text_remates) + 1,
                        "texto_completo": line,
                        "scraped_at": datetime.now().isoformat()
                    })
            
            if text_remates:
                remates = text_remates
        
        # Crear resultado final
        resultado = {
            "status": "success" if remates else "success_no_data",
            "timestamp": datetime.now().isoformat(),
            "url_scraped": url,
            "page_title": current_title,
            "bot_detection": "captcha" in current_title.lower() or "bot" in current_title.lower(),
            "total_rows_found": len(unique_rows),
            "valid_remates": len(remates),
            "page_info": {
                "html_length": page_source_length,
                "title": current_title
            },
            "remates": remates[:100]  # Primeros 100 resultados
        }
        
        # Guardar resultado
        output_file = "remates_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Scraping completado: {len(remates)} remates encontrados")
        
        # Outputs para GitHub Actions
        print(f"total_remates={len(remates)}")
        print(f"status={'success' if remates else 'success_no_data'}")
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
    print("=" * 50)
    print("RESULTADO FINAL:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
