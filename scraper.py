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

# Configuración global
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://remaju.pj.gob.pe"
MAIN_URL = f"{BASE_URL}/remaju/pages/publico/remateExterno.xhtml"
MAX_DETAILS = int(os.environ.get('MAX_DETAILS', '5'))
HEADLESS = os.environ.get('HEADLESS', 'true').lower() == 'true'

# ARCHIVO ESPECÍFICO QUE ESPERA EL CI/CD
RESULT_FILE = 'remates_result.json'

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
    """Configurar driver Chrome para CI/CD"""
    try:
        chrome_options = Options()
        
        # Configuración obligatoria para CI/CD
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-javascript-harmony-shipping")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # User agent
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Linux; x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Configuración JavaScript
        chrome_options.add_argument("--enable-javascript")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(90)
        driver.implicitly_wait(10)
        
        # Anti-detección
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        logger.info("✅ Driver Chrome configurado para CI/CD")
        return driver
        
    except Exception as e:
        logger.error(f"❌ Error configurando driver: {e}")
        return None

def wait_for_primefaces_ready(driver, timeout=30):
    """Esperar que PrimeFaces esté completamente cargado"""
    try:
        logger.info("⏳ Esperando PrimeFaces...")
        
        # Esperar que PrimeFaces esté definido
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return typeof window.PrimeFaces !== 'undefined'")
        )
        
        # Esperar que no haya AJAX activo
        WebDriverWait(driver, timeout).until(
            lambda d: PrimeFacesWaitConditions.all_ajax_complete(d)
        )
        
        time.sleep(2)
        logger.info("✅ PrimeFaces listo")
        return True
        
    except:
        logger.warning("⚠️ Timeout PrimeFaces, continuando...")
        return False

def safe_get_text(element, default=""):
    """Obtener texto de forma segura"""
    for attempt in range(2):
        try:
            if element:
                text = element.get_attribute('textContent') or element.text or default
                return ' '.join(text.strip().split())
            return default
        except StaleElementReferenceException:
            if attempt == 1:
                return default
            time.sleep(0.3)
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

class REMAJUScraperForCI:
    """Scraper optimizado para CI/CD que genera remates_result.json"""
    
    def __init__(self):
        self.driver = None
        self.main_page_url = ""
        self.stats = {
            'start_time': datetime.now(),
            'total_remates': 0,
            'remates_with_details': 0,
            'errors': 0
        }
    
    def setup(self):
        """Configurar scraper para CI/CD"""
        try:
            self.driver = create_chrome_driver()
            if not self.driver:
                return False
            return True
        except Exception as e:
            logger.error(f"❌ Error en setup: {e}")
            return False
    
    def navigate_to_main_page(self):
        """Navegar a página principal"""
        try:
            logger.info("🌐 Navegando a REMAJU...")
            self.driver.get(MAIN_URL)
            
            # Esperar carga básica
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Esperar PrimeFaces
            wait_for_primefaces_ready(self.driver, timeout=30)
            
            self.main_page_url = self.driver.current_url
            logger.info(f"✅ Página cargada: {self.main_page_url}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error navegando: {e}")
            return False
    
    def extract_remates(self):
        """Extraer remates de forma robusta"""
        remates = []
        try:
            logger.info("📋 Extrayendo remates...")
            
            # Esperar contenido
            time.sleep(5)
            
            # Obtener texto completo de la página
            try:
                body = self.driver.find_element(By.TAG_NAME, "body")
                body_text = safe_get_text(body)
                logger.info(f"📄 Texto de página obtenido: {len(body_text)} caracteres")
            except Exception as e:
                logger.error(f"❌ No se pudo obtener texto: {e}")
                return []
            
            # Extraer números de remate
            remate_numbers = re.findall(r'Remate\s+N°?\s*(\d+)', body_text, re.IGNORECASE)
            unique_numbers = list(set(remate_numbers))[:20]  # Máximo 20
            
            logger.info(f"🔍 Números encontrados: {len(unique_numbers)}")
            if not unique_numbers:
                logger.warning("⚠️ No se encontraron números de remate")
                return []
            
            # Buscar en tablas/elementos si hay contenido estructurado
            structured_remates = self.extract_from_elements(unique_numbers)
            if structured_remates:
                remates.extend(structured_remates)
            
            # Fallback: crear remates básicos
            if not remates:
                remates = self.extract_from_text(body_text, unique_numbers)
            
            self.stats['total_remates'] = len(remates)
            logger.info(f"📊 Total extraído: {len(remates)} remates")
            
            return remates
            
        except Exception as e:
            logger.error(f"❌ Error en extracción: {e}")
            return []
    
    def extract_from_elements(self, unique_numbers):
        """Intentar extraer desde elementos estructurados"""
        remates = []
        try:
            # Buscar tablas
            table_selectors = [
                "//table//tbody//tr",
                "//div[contains(@class, 'ui-datatable')]//tbody//tr",
                "//tr[td]"
            ]
            
            for selector in table_selectors:
                try:
                    rows = self.driver.find_elements(By.XPATH, selector)
                    if rows:
                        logger.info(f"🎯 Procesando {len(rows)} filas de {selector}")
                        
                        for i, row in enumerate(rows[:15]):  # Máximo 15 filas
                            try:
                                row_text = safe_get_text(row)
                                
                                # Buscar número en la fila
                                numero_match = re.search(r'Remate\s+N°?\s*(\d+)', row_text, re.IGNORECASE)
                                if not numero_match:
                                    numero_match = re.search(r'(\d{4,6})', row_text)
                                
                                if numero_match and numero_match.group(1) in unique_numbers:
                                    numero = numero_match.group(1)
                                    
                                    # Extraer información
                                    precio_texto, precio_numerico, moneda = extract_price_info(row_text)
                                    
                                    fecha_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', row_text)
                                    fecha = fecha_match.group(1) if fecha_match else ""
                                    
                                    ubicacion = ""
                                    for ciudad in ['LIMA', 'CALLAO', 'AREQUIPA', 'CUSCO', 'TRUJILLO']:
                                        if ciudad in row_text.upper():
                                            ubicacion = ciudad
                                            break
                                    
                                    # Verificar que no existe ya
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
                                            'extraction_method': 'table_structured'
                                        }
                                        
                                        remates.append(remate_data)
                                        logger.info(f"✅ Remate estructurado {numero}: {ubicacion}")
                                        
                            except Exception as e:
                                continue
                        
                        if remates:
                            break  # Si encontró algo, no buscar más
                            
                except Exception as e:
                    continue
                    
        except Exception as e:
            logger.warning(f"⚠️ Error en extracción estructurada: {e}")
        
        return remates
    
    def extract_from_text(self, body_text, unique_numbers):
        """Extraer desde texto plano"""
        remates = []
        try:
            logger.info("🔄 Extracción desde texto plano...")
            
            for i, numero in enumerate(unique_numbers):
                try:
                    # Buscar contexto del número
                    pattern = rf'Remate\s+N°?\s*{numero}.*?(?=Remate\s+N°?|\Z)'
                    context_match = re.search(pattern, body_text, re.IGNORECASE | re.DOTALL)
                    context = context_match.group(0) if context_match else ""
                    
                    if len(context) < 30:
                        # Buscar contexto más amplio
                        lines = body_text.split('\n')
                        for line_idx, line in enumerate(lines):
                            if numero in line:
                                start = max(0, line_idx - 2)
                                end = min(len(lines), line_idx + 3)
                                context = ' '.join(lines[start:end])
                                break
                    
                    # Extraer información
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
                        'button_index': i,
                        'extraction_method': 'text_fallback'
                    }
                    
                    remates.append(remate_data)
                    logger.info(f"✅ Remate texto {numero}: {ubicacion}")
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error procesando {numero}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"❌ Error en extracción de texto: {e}")
        
        return remates
    
    def navigate_to_detail(self, remate_data):
        """Navegar al detalle de forma robusta"""
        try:
            numero_remate = remate_data.get('numero_remate')
            logger.info(f"🔍 Navegando al detalle: {numero_remate}")
            
            initial_url = self.driver.current_url
            
            # Re-buscar botones
            button_selectors = [
                "//button[contains(@class, 'ui-button')]",
                "//span[contains(@class, 'ui-button')]", 
                "//a[contains(@class, 'ui-button')]",
                "//button",
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
            
            logger.info(f"📊 Botones encontrados: {len(all_buttons)}")
            
            if not all_buttons:
                logger.warning("⚠️ No se encontraron botones")
                return False
            
            # Probar botones
            button_index = remate_data.get('button_index', 0)
            indices_to_try = [button_index, 0, 1, 2]
            
            for idx in indices_to_try:
                if idx >= len(all_buttons):
                    continue
                    
                try:
                    button = all_buttons[idx]
                    logger.info(f"🎯 Probando botón {idx}")
                    
                    # Click con JavaScript
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                    time.sleep(1)
                    self.driver.execute_script("arguments[0].click();", button)
                    
                    # Esperar cambio
                    if self.wait_for_change(initial_url):
                        logger.info(f"✅ Éxito con botón {idx}")
                        return True
                    else:
                        # Regresar si cambió URL pero no hay detalle
                        if self.driver.current_url != initial_url:
                            self.driver.get(self.main_page_url)
                            wait_for_primefaces_ready(self.driver)
                            time.sleep(2)
                        
                except Exception as e:
                    logger.warning(f"⚠️ Error con botón {idx}: {e}")
                    continue
            
            logger.warning(f"⚠️ No se pudo navegar al detalle: {numero_remate}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error en navegación: {e}")
            return False
    
    def wait_for_change(self, initial_url, timeout=10):
        """Esperar cambio de navegación o contenido"""
        try:
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                current_url = self.driver.current_url
                
                # URL cambió
                if current_url != initial_url:
                    time.sleep(2)
                    wait_for_primefaces_ready(self.driver)
                    return True
                
                # Contenido de detalle apareció
                try:
                    body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body")).lower()
                    detail_indicators = [
                        'expediente', 'tasación', 'distrito judicial',
                        'órgano jurisdiccional', 'juez', 'materia'
                    ]
                    
                    detail_count = sum(1 for indicator in detail_indicators if indicator in body_text)
                    if detail_count >= 2:
                        return True
                except:
                    pass
                
                time.sleep(0.5)
            
            return False
            
        except:
            return False
    
    def extract_detail(self):
        """Extraer información de detalle"""
        try:
            logger.info("📋 Extrayendo detalle...")
            
            wait_for_primefaces_ready(self.driver, timeout=10)
            
            body_text = ""
            try:
                body = self.driver.find_element(By.TAG_NAME, "body")
                body_text = safe_get_text(body)
            except:
                return {'error': 'No se pudo obtener texto del detalle'}
            
            # Extraer campos básicos
            detail_info = {
                'expediente': self.extract_field(body_text, ['Expediente', 'N° Expediente']),
                'distrito_judicial': self.extract_field(body_text, ['Distrito Judicial']),
                'organo_jurisdiccional': self.extract_field(body_text, ['Órgano Jurisdiccional', 'Órgano Jurisdisccional']),
                'juez': self.extract_field(body_text, ['Juez']),
                'precio_base': self.extract_field(body_text, ['Precio Base']),
                'tasacion': self.extract_field(body_text, ['Tasación']),
                'convocatoria': self.extract_field(body_text, ['Convocatoria']),
                'descripcion': self.extract_field(body_text, ['Descripción']),
                'extraction_timestamp': datetime.now().isoformat(),
                'source_url': self.driver.current_url
            }
            
            logger.info(f"✅ Detalle extraído - Expediente: {detail_info.get('expediente', 'N/A')[:30]}...")
            return detail_info
            
        except Exception as e:
            logger.error(f"❌ Error extrayendo detalle: {e}")
            return {
                'error': str(e),
                'extraction_timestamp': datetime.now().isoformat()
            }
    
    def extract_field(self, text, field_labels):
        """Extraer valor de campo"""
        for label in field_labels:
            patterns = [
                rf'{re.escape(label)}\s*:?\s*([^\n\r]+)',
                rf'{re.escape(label)}\s*[:\-]\s*([^\n\r]+)',
                rf'{re.escape(label)}([^A-Za-z].*?)(?=[A-Z][a-z]|\n|\r|$)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    value = re.sub(r'^[\s:]+', '', value)
                    if 3 < len(value) < 300:
                        return value
        return ""
    
    def save_result(self, result):
        """Guardar resultado en remates_result.json"""
        try:
            with open(RESULT_FILE, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            logger.info(f"💾 Resultado guardado en: {RESULT_FILE}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error guardando resultado: {e}")
            return False
    
    def run(self):
        """Ejecutar scraping completo"""
        try:
            logger.info("🚀 Iniciando REMAJU Scraper para CI/CD")
            
            if not self.setup():
                return self.create_error_result("Error en configuración")
            
            if not self.navigate_to_main_page():
                return self.create_error_result("Error navegando a página principal")
            
            # Extraer remates
            remates = self.extract_remates()
            
            if not remates:
                return self.create_error_result("No se encontraron remates")
            
            # Procesar detalles
            detailed_remates = []
            max_details = min(MAX_DETAILS, len(remates))
            
            logger.info(f"📊 Procesando detalles: {max_details}/{len(remates)}")
            
            for i in range(max_details):
                try:
                    remate = remates[i]
                    numero_remate = remate.get('numero_remate')
                    
                    logger.info(f"🎯 Procesando {i+1}/{max_details}: {numero_remate}")
                    
                    if self.navigate_to_detail(remate):
                        detail_info = self.extract_detail()
                        
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
                        logger.warning(f"⚠️ Sin detalle: {numero_remate}")
                    
                    # Regresar para siguiente
                    if i < max_details - 1:
                        try:
                            self.driver.get(self.main_page_url)
                            wait_for_primefaces_ready(self.driver)
                            time.sleep(2)
                        except:
                            pass
                    
                except Exception as e:
                    logger.error(f"❌ Error procesando {i}: {e}")
                    self.stats['errors'] += 1
                    continue
            
            # Crear resultado final
            result = {
                'status': 'success',
                'timestamp': datetime.now().isoformat(),
                'sistema': 'REMAJU_CI_CD',
                'fuente': MAIN_URL,
                'estadisticas': self.generate_stats(),
                'total_remates_encontrados': len(remates),
                'remates_procesados': len(detailed_remates),
                'technology_detected': 'JSF + PrimeFaces',
                'remates': detailed_remates
            }
            
            # Guardar resultado
            if self.save_result(result):
                logger.info(f"🎉 Extracción completada: {len(detailed_remates)} procesados")
                return result
            else:
                return self.create_error_result("Error guardando resultado")
            
        except Exception as e:
            logger.error(f"❌ Error en ejecución: {e}")
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
            'errores': self.stats['errors'],
            'tasa_exito_detalle': round(
                (self.stats['remates_with_details'] / max(1, self.stats['total_remates'])) * 100, 2
            ) if self.stats['total_remates'] > 0 else 0,
            'fecha_extraccion': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def create_error_result(self, error_message):
        """Crear resultado de error"""
        result = {
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'error_message': error_message,
            'estadisticas': self.generate_stats(),
            'remates': []
        }
        
        # Intentar guardar incluso si hay error
        try:
            self.save_result(result)
        except:
            pass
        
        return result

def main():
    """Función principal para CI/CD"""
    try:
        logger.info("🚀 REMAJU Scraper CI/CD - Versión Corregida")
        
        scraper = REMAJUScraperForCI()
        resultado = scraper.run()
        
        if resultado['status'] == 'success':
            stats = resultado['estadisticas']
            logger.info(f"🎉 ÉXITO")
            logger.info(f"📊 {stats['total_remates_encontrados']} remates encontrados")
            logger.info(f"✅ {stats['remates_con_detalle_exitoso']} con detalle extraído")
            logger.info(f"⏱️ Duración: {stats['duracion_segundos']} segundos")
            logger.info(f"📁 Archivo: {RESULT_FILE}")
            
            print(f"SUCCESS: {stats['total_remates_encontrados']} remates, {stats['remates_con_detalle_exitoso']} detalles")
            return 0
        else:
            logger.error(f"❌ ERROR: {resultado['error_message']}")
            print(f"ERROR: {resultado['error_message']}")
            return 1
        
    except Exception as e:
        logger.error(f"❌ Error crítico: {e}")
        
        # Crear archivo de error mínimo para el CI/CD
        try:
            error_result = {
                'status': 'error',
                'timestamp': datetime.now().isoformat(),
                'error_message': str(e),
                'remates': []
            }
            with open(RESULT_FILE, 'w', encoding='utf-8') as f:
                json.dump(error_result, f, ensure_ascii=False, indent=2)
        except:
            pass
        
        print(f"CRITICAL ERROR: {str(e)}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
