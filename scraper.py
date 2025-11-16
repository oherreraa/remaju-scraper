import json
import os
import time
import logging
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
    """Configurar Chrome driver para GitHub Actions"""
    chrome_options = Options()
    
    # Opciones necesarias para GitHub Actions
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage') 
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-web-security')
    chrome_options.add_argument('--allow-running-insecure-content')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-plugins')
    
    # En GitHub Actions, usar el Chrome que viene preinstalado
    if os.getenv('GITHUB_ACTIONS'):
        logger.info("Ejecutando en GitHub Actions")
        # GitHub Actions tiene Chrome instalado por defecto
        driver = webdriver.Chrome(options=chrome_options)
    else:
        logger.info("Ejecutando localmente")
        # Para ejecución local, intentar con webdriver-manager
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            driver = webdriver.Chrome(ChromeDriverManager().install(), options=chrome_options)
        except:
            # Fallback: usar Chrome del sistema
            driver = webdriver.Chrome(options=chrome_options)
    
    return driver

def scrape_remaju():
    """Función principal de scraping"""
    driver = None
    url = "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml"
    
    try:
        logger.info("🚀 Iniciando scraping de REMAJU...")
        driver = setup_driver()
        
        logger.info(f"Navegando a: {url}")
        driver.get(url)
        
        # Esperar que cargue la página
        logger.info("Esperando que cargue la página...")
        time.sleep(5)
        
        # Obtener el contenido de la página para debug
        page_source_length = len(driver.page_source)
        logger.info(f"Longitud del HTML: {page_source_length}")
        
        # Buscar tablas de diferentes formas
        logger.info("Buscando elementos de tabla...")
        
        # Intentar diferentes selectores
        possible_selectors = [
            "table tbody tr",
            "table tr", 
            ".datatable tbody tr",
            ".tabla tbody tr",
            "[id*='table'] tr",
            "[class*='table'] tr",
            "tr"
        ]
        
        rows_found = []
        for selector in possible_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    logger.info(f"Encontrados {len(elements)} elementos con selector: {selector}")
                    rows_found = elements
                    break
            except Exception as e:
                logger.warning(f"Error con selector {selector}: {e}")
                continue
        
        # Si no encontramos nada, hacer screenshot para debug
        if not rows_found:
            logger.warning("No se encontraron filas de tabla")
            # Buscar cualquier elemento con texto
            text_elements = driver.find_elements(By.XPATH, "//*[text()]")
            logger.info(f"Elementos con texto encontrados: {len(text_elements)}")
        
        # Procesar los datos encontrados
        remates = []
        valid_rows = 0
        
        for i, row in enumerate(rows_found):
            try:
                # Obtener todas las celdas
                cells = row.find_elements(By.TAG_NAME, "td")
                if not cells:
                    cells = row.find_elements(By.TAG_NAME, "th")
                
                if len(cells) >= 2:  # Al menos 2 columnas
                    cell_texts = [cell.text.strip() for cell in cells]
                    
                    # Filtrar filas que tengan contenido real
                    if any(text and len(text) > 2 for text in cell_texts):
                        remate = {
                            "index": valid_rows + 1,
                            "columna_1": cell_texts[0] if len(cell_texts) > 0 else "",
                            "columna_2": cell_texts[1] if len(cell_texts) > 1 else "",
                            "columna_3": cell_texts[2] if len(cell_texts) > 2 else "",
                            "columna_4": cell_texts[3] if len(cell_texts) > 3 else "",
                            "columna_5": cell_texts[4] if len(cell_texts) > 4 else "",
                            "columna_6": cell_texts[5] if len(cell_texts) > 5 else "",
                            "total_columns": len(cell_texts),
                            "scraped_at": datetime.now().isoformat()
                        }
                        remates.append(remate)
                        valid_rows += 1
                        
            except Exception as e:
                logger.warning(f"Error procesando fila {i}: {e}")
                continue
        
        # Crear resultado final
        resultado = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "url_scraped": url,
            "total_elements_found": len(rows_found),
            "valid_remates": len(remates),
            "page_info": {
                "html_length": page_source_length,
                "title": driver.title
            },
            "remates": remates[:50]  # Limitar a primeros 50 para evitar archivos muy grandes
        }
        
        # Guardar resultado
        output_file = "remates_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Scraping exitoso: {len(remates)} remates encontrados")
        logger.info(f"📄 Resultado guardado en: {output_file}")
        
        # Outputs para GitHub Actions
        print(f"total_remates={len(remates)}")
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
        
        logger.error(f"❌ Error en scraping: {e}")
        
        # Guardar error
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
