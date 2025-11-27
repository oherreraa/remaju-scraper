#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sys
import time
import logging
import re
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, JavascriptException, StaleElementReferenceException, NoSuchElementException, ElementNotInteractableException
from selenium.webdriver.common.action_chains import ActionChains

# Configuración global
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://remaju.pj.gob.pe"
MAIN_URL = f"{BASE_URL}/remaju/pages/publico/remateExterno.xhtml"
MAX_DETAILS = int(os.environ.get('MAX_DETAILS', '3'))
HEADLESS = os.environ.get('HEADLESS', 'false').lower() == 'true'

# Directorios seguros para guardar archivos
OUTPUT_DIR = '/mnt/user-data/outputs'
DEBUG_FILE = f'{OUTPUT_DIR}/remaju_debug.json'
RESULT_FILE = f'{OUTPUT_DIR}/remates_result_final.json'

class PrimeFacesWaitConditions:
    """Condiciones de espera específicas para PrimeFaces"""
    
    @staticmethod
    def primefaces_ajax_complete(driver):
        try:
            return driver.execute_script("""
                return (typeof window.PrimeFaces !== 'undefined') 
                    ? window.PrimeFaces.ajax.Queue.isEmpty() 
                    : true;
            """)
        except:
            return True
    
    @staticmethod 
    def jquery_ajax_complete(driver):
        try:
            return driver.execute_script("""
                return (typeof window.jQuery !== 'undefined') 
                    ? (jQuery.active === 0) 
                    : true;
            """)
        except:
            return True
    
    @staticmethod
    def document_ready_complete(driver):
        try:
            return driver.execute_script("return document.readyState") == "complete"
        except:
            return True
    
    @staticmethod
    def all_ajax_complete(driver):
        return (PrimeFacesWaitConditions.primefaces_ajax_complete(driver) and 
                PrimeFacesWaitConditions.jquery_ajax_complete(driver) and
                PrimeFacesWaitConditions.document_ready_complete(driver))

def create_chrome_driver():
    """Configurar driver Chrome optimizado"""
    try:
        chrome_options = Options()
        if HEADLESS:
            chrome_options.add_argument("--headless=new")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage") 
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        chrome_options.add_argument("--enable-javascript")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(120)
        driver.implicitly_wait(10)
        
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver
    except Exception as e:
        logger.error(f"Error configurando driver: {e}")
        return None

def wait_for_primefaces_ready(driver, timeout=30):
    """Esperar que PrimeFaces esté completamente cargado"""
    try:
        logger.info("⏳ Esperando PrimeFaces...")
        
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return typeof window.PrimeFaces !== 'undefined'")
        )
        
        WebDriverWait(driver, timeout).until(
            lambda d: PrimeFacesWaitConditions.all_ajax_complete(d)
        )
        
        time.sleep(2)  # Estabilización
        logger.info("✅ PrimeFaces listo")
        return True
        
    except:
        logger.warning("⚠️ Timeout PrimeFaces, continuando...")
        return False

def safe_get_text(element, default=""):
    """Obtener texto de forma ultra-segura"""
    for attempt in range(3):
        try:
            if element:
                text = element.get_attribute('textContent') or element.text or default
                return ' '.join(text.strip().split())
            return default
        except StaleElementReferenceException:
            if attempt == 2:
                logger.warning("⚠️ Stale element después de 3 intentos")
                return default
            time.sleep(0.5)
        except:
            return default
    return default

def extract_price_info(text):
    """Extraer precio y moneda"""
    if not text:
        return "", 0.0, ""
    
    patterns = [
        (r'Precio\s+Base\s+(S/\.|\$|USD)\s*([\d,]+\.?\d*)', 1, 2),
        (r'(S/\.|\$|USD)\s*([\d,]+\.?\d*)', 1, 2), 
        (r'([\d,]+\.?\d*)\s*(SOLES|DOLARES|USD)', 2, 1),
    ]
    
    for pattern, currency_group, amount_group in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            currency_text = match.group(currency_group)
            currency = "USD" if currency_text in ["$", "USD", "DOLARES"] else "S/."
            
            amount_str = match.group(amount_group).replace(',', '')
            try:
                amount = float(amount_str)
                return f"{currency} {match.group(amount_group)}", amount, currency
            except:
                return text, 0.0, currency
    
    return text, 0.0, ""

class REMAJUScraperUltraRobust:
    """Scraper ultra-robusto para REMAJU"""
    
    def __init__(self):
        self.driver = None
        self.main_page_url = ""
        self.stats = {
            'start_time': datetime.now(),
            'total_remates': 0,
            'remates_with_details': 0,
            'errors': 0,
            'stale_element_errors': 0,
            'navigation_errors': 0,
            'ajax_calls_detected': 0
        }
    
    def setup(self):
        """Configurar scraper"""
        try:
            self.driver = create_chrome_driver()
            if not self.driver:
                return False
            logger.info("✅ Driver configurado")
            return True
        except Exception as e:
            logger.error(f"❌ Error en setup: {e}")
            return False
    
    def navigate_to_main_page(self):
        """Navegar a página principal"""
        try:
            logger.info("🌐 Navegando a REMAJU...")
            self.driver.get(MAIN_URL)
            
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            wait_for_primefaces_ready(self.driver, timeout=40)
            
            self.main_page_url = self.driver.current_url
            logger.info(f"✅ Página cargada: {self.main_page_url}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error navegando: {e}")
            return False
    
    def extract_remates_ultra_safe(self):
        """Extracción ultra-segura de remates"""
        remates = []
        try:
            logger.info("📋 Extrayendo remates (modo ultra-seguro)...")
            
            # Esperar componentes
            time.sleep(3)
            
            # Obtener todo el texto de la página
            body_text = ""
            try:
                body = self.driver.find_element(By.TAG_NAME, "body")
                body_text = safe_get_text(body)
            except:
                logger.error("❌ No se pudo obtener texto de la página")
                return []
            
            # Buscar números de remate en el texto
            remate_numbers = re.findall(r'Remate\s+N°?\s*(\d+)', body_text, re.IGNORECASE)
            unique_numbers = list(set(remate_numbers))
            
            logger.info(f"🔍 Números de remate encontrados: {len(unique_numbers)}")
            
            # También intentar buscar en elementos de tabla/componentes
            try:
                self.find_elements_safe(remates, unique_numbers)
            except Exception as e:
                logger.warning(f"⚠️ Error buscando en elementos: {e}")
            
            # Fallback: crear remates básicos desde números encontrados
            if not remates:
                for i, numero in enumerate(unique_numbers[:20]):  # Máximo 20
                    try:
                        context = self.extract_context_for_number(body_text, numero)
                        precio_texto, precio_numerico, moneda = extract_price_info(context)
                        
                        fecha_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', context)
                        fecha = fecha_match.group(1) if fecha_match else ""
                        
                        ubicacion = ""
                        for ciudad in ['LIMA', 'CALLAO', 'AREQUIPA', 'CUSCO', 'TRUJILLO', 'PIURA']:
                            if ciudad in context.upper():
                                ubicacion = ciudad
                                break
                        
                        remate_data = {
                            'numero_remate': numero,
                            'titulo_card': f"Remate N° {numero}",
                            'ubicacion_corta': ubicacion,
                            'fecha_presentacion_oferta': fecha,
                            'precio_base_texto': precio_texto,
                            'precio_base_numerico': precio_numerico,
                            'moneda': moneda,
                            'button_index': i,  # Índice para encontrar botón
                            'extraction_method': 'ultra_safe_fallback'
                        }
                        
                        remates.append(remate_data)
                        logger.info(f"✅ Remate {numero}: {ubicacion}")
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Error procesando número {numero}: {e}")
                        continue
            
            self.stats['total_remates'] = len(remates)
            logger.info(f"📊 Total extraído: {len(remates)} remates")
            
            return remates
            
        except Exception as e:
            logger.error(f"❌ Error en extracción ultra-segura: {e}")
            return []
    
    def find_elements_safe(self, remates, unique_numbers):
        """Buscar elementos de tabla/componentes de forma segura"""
        try:
            # Buscar tablas y filas
            table_selectors = [
                "//table//tbody//tr",
                "//div[contains(@class, 'ui-datatable')]//tbody//tr",
                "//tr"
            ]
            
            for selector in table_selectors:
                try:
                    rows = self.driver.find_elements(By.XPATH, selector)
                    if rows:
                        logger.info(f"🎯 Encontradas {len(rows)} filas: {selector}")
                        
                        for i, row in enumerate(rows[:30]):  # Máximo 30 filas
                            try:
                                row_text = safe_get_text(row)
                                
                                # Buscar número de remate en la fila
                                for numero in unique_numbers:
                                    if numero in row_text:
                                        # Extraer información de la fila
                                        precio_texto, precio_numerico, moneda = extract_price_info(row_text)
                                        
                                        fecha_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', row_text)
                                        fecha = fecha_match.group(1) if fecha_match else ""
                                        
                                        ubicacion = ""
                                        for ciudad in ['LIMA', 'CALLAO', 'AREQUIPA', 'CUSCO', 'TRUJILLO']:
                                            if ciudad in row_text.upper():
                                                ubicacion = ciudad
                                                break
                                        
                                        # Verificar si ya existe
                                        if not any(r['numero_remate'] == numero for r in remates):
                                            remate_data = {
                                                'numero_remate': numero,
                                                'titulo_card': f"Remate N° {numero}",
                                                'ubicacion_corta': ubicacion,
                                                'fecha_presentacion_oferta': fecha,
                                                'precio_base_texto': precio_texto,
                                                'precio_base_numerico': precio_numerico,
                                                'moneda': moneda,
                                                'button_index': i,
                                                'extraction_method': 'table_safe'
                                            }
                                            
                                            remates.append(remate_data)
                                            logger.info(f"✅ Remate tabla {numero}: {ubicacion}")
                                            
                                        break  # Solo uno por fila
                                        
                            except Exception as e:
                                continue  # Continuar con siguiente fila
                        
                        if remates:
                            break  # Si encontró remates, no buscar más
                            
                except Exception as e:
                    continue  # Continuar con siguiente selector
                    
        except Exception as e:
            logger.warning(f"⚠️ Error en find_elements_safe: {e}")
    
    def extract_context_for_number(self, body_text, numero):
        """Extraer contexto alrededor de un número de remate"""
        try:
            # Buscar contexto expandido alrededor del número
            patterns = [
                rf'Remate\s+N°?\s*{numero}.*?(?=Remate\s+N°?|\Z)',
                rf'.*?{numero}.*?(?=\d{{4,6}}|\Z)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, body_text, re.IGNORECASE | re.DOTALL)
                if match and len(match.group(0)) > 50:
                    return match.group(0)
            
            # Fallback: buscar líneas alrededor del número
            lines = body_text.split('\n')
            for i, line in enumerate(lines):
                if numero in line:
                    start = max(0, i - 3)
                    end = min(len(lines), i + 4)
                    return ' '.join(lines[start:end])
            
            return ""
            
        except Exception as e:
            return ""
    
    def navigate_to_detail_ultra_safe(self, remate_data):
        """Navegación ultra-segura al detalle"""
        try:
            numero_remate = remate_data.get('numero_remate')
            logger.info(f"🔍 Navegando al detalle (ultra-seguro): {numero_remate}")
            
            initial_url = self.driver.current_url
            
            # Re-encontrar botones cada vez para evitar stale reference
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    logger.info(f"🎯 Intento {attempt + 1}/{max_attempts} - Re-buscando botones")
                    
                    # Re-encontrar todos los botones relevantes
                    button_selectors = [
                        "//button[contains(@class, 'ui-button')]",
                        "//span[contains(@class, 'ui-button')]",
                        "//a[contains(@class, 'ui-button')]",
                        "//button[contains(text(), 'Detalle')]",
                        "//a[contains(text(), 'Detalle')]",
                        "//button[contains(text(), 'Ver')]",
                        "//input[@type='submit']"
                    ]
                    
                    all_buttons = []
                    for selector in button_selectors:
                        try:
                            buttons = self.driver.find_elements(By.XPATH, selector)
                            for button in buttons:
                                try:
                                    if button.is_displayed() and button.is_enabled():
                                        btn_text = safe_get_text(button).lower()
                                        if any(keyword in btn_text for keyword in ['detalle', 'detail', 'ver', 'consultar', 'info']):
                                            all_buttons.append(button)
                                except:
                                    continue
                        except:
                            continue
                    
                    logger.info(f"📊 Botones encontrados en intento {attempt + 1}: {len(all_buttons)}")
                    
                    if not all_buttons:
                        logger.warning(f"⚠️ No se encontraron botones en intento {attempt + 1}")
                        continue
                    
                    # Probar botones por índice
                    button_index = remate_data.get('button_index', 0)
                    indices_to_try = [button_index, 0, 1, 2, 3, 4]  # Probar varios índices
                    
                    button_clicked = False
                    for idx in indices_to_try:
                        if idx >= len(all_buttons):
                            continue
                            
                        try:
                            button = all_buttons[idx]
                            logger.info(f"🎯 Probando botón índice {idx}")
                            
                            # Scroll y click con JavaScript para mayor confiabilidad
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                            time.sleep(1)
                            self.driver.execute_script("arguments[0].click();", button)
                            
                            # Esperar respuesta
                            if self.wait_for_navigation_or_content_change(initial_url):
                                logger.info(f"✅ Éxito con botón índice {idx}")
                                button_clicked = True
                                break
                            else:
                                logger.info(f"⚠️ Botón {idx} no generó cambios")
                                # Intentar regresar si cambió la URL
                                if self.driver.current_url != initial_url:
                                    self.driver.get(self.main_page_url)
                                    wait_for_primefaces_ready(self.driver)
                                    time.sleep(2)
                                
                        except Exception as e:
                            logger.warning(f"⚠️ Error con botón {idx}: {e}")
                            self.stats['navigation_errors'] += 1
                            continue
                    
                    if button_clicked:
                        return True
                    
                    # Si no funcionó, intentar de nuevo después de refresh
                    if attempt < max_attempts - 1:
                        logger.info("🔄 Refresh y reintento...")
                        self.driver.get(self.main_page_url)
                        wait_for_primefaces_ready(self.driver)
                        time.sleep(3)
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error en intento {attempt + 1}: {e}")
                    if attempt < max_attempts - 1:
                        time.sleep(2)
                    continue
            
            logger.error(f"❌ No se pudo navegar al detalle después de {max_attempts} intentos: {numero_remate}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error en navegación ultra-segura: {e}")
            return False
    
    def wait_for_navigation_or_content_change(self, initial_url, timeout=15):
        """Esperar cambio de navegación o contenido"""
        try:
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    current_url = self.driver.current_url
                    
                    # Verificar cambio de URL
                    if current_url != initial_url:
                        logger.info("🔄 URL cambió - navegación detectada")
                        time.sleep(2)
                        wait_for_primefaces_ready(self.driver)
                        return True
                    
                    # Verificar contenido de detalle aparecido
                    body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body")).lower()
                    detail_indicators = [
                        'expediente', 'tasación', 'partida', 'distrito judicial',
                        'órgano jurisdiccional', 'cronograma', 'inmuebles',
                        'resolución', 'juez', 'materia', 'convocatoria'
                    ]
                    
                    detail_count = sum(1 for indicator in detail_indicators if indicator in body_text)
                    if detail_count >= 3:  # Al menos 3 indicadores de detalle
                        logger.info(f"🔄 Contenido detalle detectado ({detail_count} indicadores)")
                        time.sleep(1)
                        return True
                    
                except:
                    pass
                
                time.sleep(0.5)
            
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ Error esperando navegación: {e}")
            return False
    
    def extract_detail_ultra_safe(self):
        """Extraer detalle de forma ultra-segura"""
        try:
            logger.info("📋 Extrayendo detalle (ultra-seguro)...")
            
            wait_for_primefaces_ready(self.driver, timeout=10)
            
            body_text = ""
            try:
                body = self.driver.find_element(By.TAG_NAME, "body")
                body_text = safe_get_text(body)
            except:
                logger.error("❌ No se pudo obtener texto del detalle")
                return {'error': 'No se pudo obtener texto de la página de detalle'}
            
            # Extracción de campos con múltiples patrones
            detail_info = {
                'expediente': self.extract_field_robust(body_text, ['Expediente', 'N° Expediente', 'Exp']),
                'distrito_judicial': self.extract_field_robust(body_text, ['Distrito Judicial']),
                'organo_jurisdiccional': self.extract_field_robust(body_text, ['Órgano Jurisdiccional', 'Órgano Jurisdisccional']),
                'juez': self.extract_field_robust(body_text, ['Juez']),
                'precio_base': self.extract_field_robust(body_text, ['Precio Base']),
                'tasacion': self.extract_field_robust(body_text, ['Tasación']),
                'convocatoria': self.extract_field_robust(body_text, ['Convocatoria']),
                'descripcion': self.extract_field_robust(body_text, ['Descripción']),
                'extraction_timestamp': datetime.now().isoformat(),
                'source_url': self.driver.current_url,
                'content_length': len(body_text)
            }
            
            logger.info(f"✅ Detalle extraído - Expediente: {detail_info.get('expediente', 'N/A')[:50]}...")
            return detail_info
            
        except Exception as e:
            logger.error(f"❌ Error extrayendo detalle ultra-seguro: {e}")
            return {
                'error': str(e),
                'extraction_timestamp': datetime.now().isoformat(),
                'source_url': self.driver.current_url if self.driver else 'unknown'
            }
    
    def extract_field_robust(self, text, field_labels):
        """Extracción robusta de campos"""
        for label in field_labels:
            patterns = [
                rf'{re.escape(label)}\s*:?\s*([^\n\r]+)',
                rf'{re.escape(label)}\s*[:\-]\s*([^\n\r]+)', 
                rf'{re.escape(label)}([^A-Za-z].*?)(?=[A-Z][a-z]{3,}|\n|\r|$)',
                rf'(?<=\s){re.escape(label)}\s+([A-Z0-9].*?)(?=\s+[A-Z][a-z]|\n|\r|$)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    value = match.group(1).strip()
                    value = re.sub(r'^[\s:]+', '', value)
                    value = re.sub(r'\s+', ' ', value)  # Limpiar espacios múltiples
                    if 3 < len(value) < 500:  # Valor razonable
                        return value
        return ""
    
    def save_safe(self, data, filename):
        """Guardar archivo de forma segura"""
        try:
            # Asegurar que el directorio existe
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            
            filepath = f"{OUTPUT_DIR}/{filename}"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"💾 Archivo guardado: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"❌ Error guardando {filename}: {e}")
            return None
    
    def run_extraction(self):
        """Ejecutar extracción ultra-robusta completa"""
        try:
            logger.info("🚀 Iniciando extracción REMAJU ultra-robusta")
            
            if not self.setup():
                return self.create_error_result("Error en configuración")
            
            if not self.navigate_to_main_page():
                return self.create_error_result("Error navegando a página principal")
            
            # Extraer remates
            remates = self.extract_remates_ultra_safe()
            
            if not remates:
                return self.create_error_result("No se encontraron remates")
            
            # Extraer detalles
            detailed_remates = []
            max_details = min(MAX_DETAILS, len(remates))
            
            logger.info(f"📊 Procesando detalles ultra-seguros: {max_details}/{len(remates)}")
            
            for i in range(max_details):
                try:
                    remate = remates[i]
                    numero_remate = remate.get('numero_remate')
                    
                    logger.info(f"🎯 Procesando {i+1}/{max_details}: {numero_remate}")
                    
                    if self.navigate_to_detail_ultra_safe(remate):
                        detail_info = self.extract_detail_ultra_safe()
                        
                        complete_remate = {
                            'numero_remate': numero_remate,
                            'basic_info': remate,
                            'detalle': detail_info,
                            'extraction_success': True
                        }
                        
                        detailed_remates.append(complete_remate)
                        self.stats['remates_with_details'] += 1
                        
                        logger.info(f"✅ Detalle extraído: {numero_remate}")
                    else:
                        failed_remate = {
                            'numero_remate': numero_remate,
                            'basic_info': remate,
                            'detalle': {'error': 'No se pudo acceder al detalle'},
                            'extraction_success': False
                        }
                        detailed_remates.append(failed_remate)
                        logger.warning(f"⚠️ No se pudo extraer detalle: {numero_remate}")
                    
                    # Regresar para el siguiente
                    if i < max_details - 1:
                        try:
                            logger.info("🔙 Regresando a página principal...")
                            self.driver.get(self.main_page_url)
                            wait_for_primefaces_ready(self.driver)
                            time.sleep(2)
                        except Exception as e:
                            logger.warning(f"⚠️ Error regresando: {e}")
                    
                except Exception as e:
                    logger.error(f"❌ Error procesando remate {i}: {e}")
                    self.stats['errors'] += 1
                    continue
            
            result = {
                'status': 'success',
                'timestamp': datetime.now().isoformat(),
                'sistema': 'REMAJU_ULTRA_ROBUST',
                'fuente': MAIN_URL,
                'estadisticas': self.generate_stats(),
                'total_remates_encontrados': len(remates),
                'remates_procesados': len(detailed_remates),
                'technology_detected': 'JSF + PrimeFaces (Ultra-Robust)',
                'remates': detailed_remates
            }
            
            # Guardar resultado de forma segura
            result_file = self.save_safe(result, 'remates_ultra_robust_result.json')
            
            logger.info(f"🎉 Extracción ultra-robusta completada: {len(detailed_remates)} procesados")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error en extracción ultra-robusta: {e}")
            return self.create_error_result(str(e))
        
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("🔒 Driver cerrado")
    
    def generate_stats(self):
        """Generar estadísticas"""
        duration = (datetime.now() - self.stats['start_time']).total_seconds()
        return {
            'duracion_segundos': round(duration, 2),
            'total_remates_encontrados': self.stats['total_remates'],
            'remates_con_detalle_exitoso': self.stats['remates_with_details'],
            'errores_totales': self.stats['errors'],
            'errores_stale_element': self.stats['stale_element_errors'],
            'errores_navegacion': self.stats['navigation_errors'],
            'tasa_exito_detalle': round(
                (self.stats['remates_with_details'] / max(1, self.stats['total_remates'])) * 100, 2
            ),
            'technology': 'JSF + PrimeFaces Ultra-Robust',
            'fecha_extraccion': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def create_error_result(self, error_message):
        """Crear resultado de error"""
        return {
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'error_message': error_message,
            'technology_detected': 'JSF + PrimeFaces Ultra-Robust',
            'estadisticas': self.generate_stats(),
            'remates': []
        }

def main():
    """Función principal ultra-robusta"""
    try:
        logger.info("🚀 Iniciando REMAJU Scraper Ultra-Robusto")
        
        scraper = REMAJUScraperUltraRobust()
        resultado = scraper.run_extraction()
        
        # Guardar resultado con nombre único
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"{OUTPUT_DIR}/remates_ultra_robust_{timestamp}.json"
        
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(resultado, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 Resultado guardado en: {output_file}")
        except Exception as e:
            logger.error(f"❌ Error guardando resultado: {e}")
        
        # Log resultado
        if resultado['status'] == 'success':
            stats = resultado['estadisticas']
            logger.info(f"🎉 ÉXITO ULTRA-ROBUSTO")
            logger.info(f"📊 {stats['total_remates_encontrados']} remates encontrados")
            logger.info(f"✅ {stats['remates_con_detalle_exitoso']} con detalle extraído")
            logger.info(f"⚠️ {stats.get('errores_stale_element', 0)} errores stale element")
            logger.info(f"⏱️ Duración: {stats['duracion_segundos']} segundos")
            
            print(f"status=success")
            print(f"total_remates={stats['total_remates_encontrados']}")
            print(f"remates_con_detalle={stats['remates_con_detalle_exitoso']}")
            print(f"stale_errors={stats.get('errores_stale_element', 0)}")
            print(f"archivo={output_file}")
        else:
            logger.error(f"❌ ERROR ULTRA-ROBUSTO: {resultado['error_message']}")
            print(f"status=error")
            print(f"error={resultado['error_message']}")
        
        return resultado
        
    except Exception as e:
        logger.error(f"❌ Error principal ultra-robusto: {e}")
        print(f"status=error")
        print(f"error={str(e)}")
        return {'status': 'error', 'error_message': str(e)}

if __name__ == "__main__":
    result = main()
    sys.exit(0 if result.get('status') == 'success' else 1)
