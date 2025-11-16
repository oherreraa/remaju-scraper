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
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.utils import ChromeType

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
    
    # Detectar si estamos en GitHub Actions
    if os.getenv('GITHUB_ACTIONS'):
        logger.info("Ejecutando en GitHub Actions - usando Chromium")
        # Usar Chromium en GitHub Actions
        driver_path = ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
        driver = webdriver.Chrome(service=webdriver.chrome.service.Service(driver_path), 
                                options=chrome_options)
    else:
        logger.info("Ejecutando localmente - usando Chrome")
        # Usar Chrome normal en local
        driver_path = ChromeDriverManager().install()
        driver = webdriver.Chrome(service=webdriver.chrome.service.Service(driver_path), 
                                options=chrome_options)
    
    return driver

def scrape_remaju():
    """Función principal de scraping"""
    driver = None
    
    try:
        logger.info("🚀 Iniciando scraping de REMAJU...")
        driver = setup_driver()
        
        # Navegar a la página
        url = "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml"
        logger.info(f"Navegando a: {url}")
        driver.get(url)
        
        # Esperar a que cargue la tabla
        logger.info("Esperando que cargue la tabla...")
        wait = WebDriverWait(driver, 30)
        
        # Intentar diferentes selectores posibles
        table_selectors = [
            "table tbody tr",
            "table tr",
            ".table tbody tr",
            "[id*='table'] tbody tr",
            "[class*='table'] tbody tr"
        ]
        
        rows = []
        for selector in table_selectors:
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                rows = driver.find_elements(By.CSS_SELECTOR, selector)
                if rows:
                    logger.info(f"✅ Tabla encontrada con selector: {selector}")
                    break
            except:
                continue
        
        if not rows:
            logger.warning("No se encontraron filas. Intentando con tiempo extra...")
            time.sleep(10)
            # Último intento con cualquier fila de tabla
            rows = driver.find_elements(By.CSS_SELECTOR, "tr")
        
        # Extraer datos
        remates = []
        logger.info(f"Procesando {len(rows)} filas...")
        
        for i, row in enumerate(rows):
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 3:  # Al menos 3 columnas para considerar válida
                    remate = {
                        "index": i + 1,
                        "expediente": cells[0].text.strip() if len(cells) > 0 else "",
                        "demandado": cells[1].text.strip() if len(cells) > 1 else "",
                        "bien": cells[2].text.strip() if len(cells) > 2 else "",
                        "ubicacion": cells[3].text.strip() if len(cells) > 3 else "",
                        "fecha_remate": cells[4].text.strip() if len(cells) > 4 else "",
                        "valor_base": cells[5].text.strip() if len(cells) > 5 else "",
                        "scraped_at": datetime.now().isoformat()
                    }
                    
                    # Solo agregar si tiene contenido real
                    if any(remate[key] for key in ['expediente', 'demandado', 'bien'] 
                          if remate[key] and remate[key] != ""):
                        remates.append(remate)
                        
            except Exception as e:
                logger.warning(f"Error procesando fila {i}: {e}")
                continue
        
        # Crear resultado
        resultado = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "url_scraped": url,
            "total_remates": len(remates),
            "remates": remates,
            "metadata": {
                "total_rows_found": len(rows),
                "valid_remates": len(remates),
                "execution_time": time.time()
            }
        }
        
        # Guardar resultado
        output_file = "remates_result.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Scraping exitoso: {len(remates)} remates encontrados")
        logger.info(f"📄 Resultado guardado en: {output_file}")
        
        # Output para GitHub Actions
        if os.getenv('GITHUB_ACTIONS'):
            print(f"::set-output name=total_remates::{len(remates)}")
            print(f"::set-output name=status::success")
        
        return resultado
        
    except Exception as e:
        error_result = {
            "status": "error",
            "timestamp": datetime.now().isoformat(), 
            "error_message": str(e),
            "error_type": type(e).__name__,
            "url_attempted": url if 'url' in locals() else "N/A"
        }
        
        logger.error(f"❌ Error en scraping: {e}")
        
        # Guardar error
        with open('remates_result.json', 'w', encoding='utf-8') as f:
            json.dump(error_result, f, ensure_ascii=False, indent=2)
        
        if os.getenv('GITHUB_ACTIONS'):
            print(f"::set-output name=status::error") 
            print(f"::set-output name=error::{str(e)}")
            
        return error_result
        
    finally:
        if driver:
            driver.quit()
            logger.info("🔒 Driver cerrado correctamente")

if __name__ == "__main__":
    result = scrape_remaju()
    print(json.dumps(result, ensure_ascii=False, indent=2))
