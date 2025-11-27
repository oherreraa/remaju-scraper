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
from selenium.common.exceptions import TimeoutException, JavascriptException, StaleElementReferenceException, NoSuchElementException

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
        
        time.sleep(3)  # Más tiempo para estabilización
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
    """Extraer precio y moneda con patrones mejorados"""
    if not text:
        return "", 0.0, ""
    
    # Limpiar texto primero
    clean_text = re.sub(r'\s+', ' ', text.strip())
    
    patterns = [
        # Precio Base específico
        (r'Precio\s+Base[:\s]*([USD|S/\.|\$]*)\s*([\d,]+\.?\d*)', 1, 2),
        # Moneda seguida de número
        (r'(S/\.|\$|USD)\s*([\d,]+\.?\d*)', 1, 2),
        # Número seguido de moneda
        (r'([\d,]+\.?\d*)\s*(SOLES|DOLARES|USD|S/\.)', 1, 2),
        # Tasación o precio base en contexto
        (r'(?:Tasaci[óo]n|Base)[:\s]*([USD|S/\.|\$]*)\s*([\d,]+\.?\d*)', 1, 2)
    ]
    
    for pattern, currency_group, amount_group in patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            try:
                currency_text = match.group(currency_group)
                amount_text = match.group(amount_group)
                
                # Determinar moneda
                if currency_text in ["$", "USD", "DOLARES"] or "USD" in currency_text.upper():
                    currency = "USD"
                else:
                    currency = "S/."
                
                # Convertir monto
                amount_str = amount_text.replace(',', '')
                amount = float(amount_str)
                
                return f"{currency} {amount_text}", amount, currency
            except:
                continue
    
    return text, 0.0, ""

class REMAJUScraperPrecision:
    """Scraper de alta precisión para REMAJU"""
    
    def __init__(self):
        self.driver = None
        self.main_page_url = ""
        self.stats = {
            'start_time': datetime.now(),
            'total_remates': 0,
            'remates_with_details': 0,
            'extraction_precision_errors': 0,
            'field_extraction_success': {},
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
            
            # Esperar PrimeFaces con más tiempo
            wait_for_primefaces_ready(self.driver, timeout=40)
            
            self.main_page_url = self.driver.current_url
            logger.info(f"✅ Página cargada: {self.main_page_url}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error navegando: {e}")
            return False
    
    def extract_remates_precision(self):
        """Extraer remates con mayor precisión en estructura"""
        remates = []
        try:
            logger.info("📋 Extrayendo remates con precisión mejorada...")
            
            # Esperar más tiempo para que todo cargue
            time.sleep(5)
            
            # Intentar múltiples estrategias de extracción estructurada
            remates = self.extract_structured_data()
            
            if not remates:
                logger.info("🔄 Fallback a extracción de texto...")
                remates = self.extract_from_page_text()
            
            self.stats['total_remates'] = len(remates)
            logger.info(f"📊 Total extraído: {len(remates)} remates")
            
            return remates
            
        except Exception as e:
            logger.error(f"❌ Error en extracción de precisión: {e}")
            return []
    
    def extract_structured_data(self):
        """Intentar extracción estructurada mejorada"""
        remates = []
        try:
            logger.info("🎯 Intentando extracción estructurada...")
            
            # Estrategia 1: Buscar componentes PrimeFaces específicos
            primefaces_selectors = [
                "//table[contains(@class, 'ui-datatable')]",
                "//div[contains(@class, 'ui-datatable')]",
                "//div[contains(@class, 'ui-datagrid')]",
                "//div[contains(@class, 'ui-panel')]//table",
                "//form//table"
            ]
            
            for selector in primefaces_selectors:
                try:
                    tables = self.driver.find_elements(By.XPATH, selector)
                    for table in tables:
                        table_text = safe_get_text(table)
                        if 'remate' in table_text.lower() and len(table_text) > 200:
                            logger.info(f"🎯 Tabla relevante encontrada: {selector}")
                            extracted = self.extract_from_table_precise(table)
                            if extracted:
                                remates.extend(extracted)
                                logger.info(f"✅ Extraídos {len(extracted)} remates de tabla estructurada")
                                break
                    if remates:
                        break
                except Exception as e:
                    continue
            
            # Estrategia 2: Buscar filas de tabla directamente
            if not remates:
                row_selectors = [
                    "//table//tbody//tr[td[contains(text(), 'Remate') or contains(text(), '20')]]",
                    "//tr[td[contains(text(), 'Remate')]]",
                    "//div[contains(@class, 'ui-datatable')]//tr"
                ]
                
                for selector in row_selectors:
                    try:
                        rows = self.driver.find_elements(By.XPATH, selector)
                        if rows:
                            logger.info(f"🎯 Filas encontradas: {len(rows)} en {selector}")
                            extracted = self.extract_from_rows_precise(rows)
                            if extracted:
                                remates.extend(extracted)
                                logger.info(f"✅ Extraídos {len(extracted)} remates de filas")
                                break
                    except Exception as e:
                        continue
            
            return remates
            
        except Exception as e:
            logger.warning(f"⚠️ Error en extracción estructurada: {e}")
            return []
    
    def extract_from_table_precise(self, table):
        """Extraer desde tabla con mayor precisión"""
        remates = []
        try:
            # Buscar filas en la tabla
            rows = table.find_elements(By.XPATH, ".//tr")
            logger.info(f"📊 Procesando tabla con {len(rows)} filas")
            
            for i, row in enumerate(rows):
                try:
                    cells = row.find_elements(By.XPATH, ".//td")
                    if len(cells) < 2:  # Skip headers or empty rows
                        continue
                    
                    cell_texts = [safe_get_text(cell) for cell in cells]
                    combined_text = " ".join(cell_texts)
                    
                    # Buscar número de remate
                    numero_match = re.search(r'Remate\s+N°?\s*(\d+)', combined_text, re.IGNORECASE)
                    if not numero_match:
                        numero_match = re.search(r'(?:^|\s)(\d{4,6})(?:\s|$)', combined_text)
                    
                    if numero_match:
                        numero_remate = numero_match.group(1)
                        
                        # Extraer información precisa de celdas
                        precio_texto, precio_numerico, moneda = self.extract_price_from_cells(cell_texts)
                        fecha = self.extract_date_from_cells(cell_texts)
                        ubicacion = self.extract_location_from_cells(cell_texts)
                        
                        remate_data = {
                            'numero_remate': numero_remate,
                            'titulo_card': f"Remate N° {numero_remate}",
                            'ubicacion_corta': ubicacion,
                            'fecha_presentacion_oferta': fecha,
                            'precio_base_texto': precio_texto,
                            'precio_base_numerico': precio_numerico,
                            'moneda': moneda,
                            'button_index': i,
                            'cell_data': cell_texts,
                            'extraction_method': 'table_structured_precise'
                        }
                        
                        remates.append(remate_data)
                        logger.info(f"✅ Remate tabla preciso {numero_remate}: {ubicacion}")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Error procesando fila {i}: {e}")
                    continue
            
            return remates
            
        except Exception as e:
            logger.error(f"❌ Error en extracción de tabla precisa: {e}")
            return []
    
    def extract_from_rows_precise(self, rows):
        """Extraer desde filas con mayor precisión"""
        remates = []
        try:
            logger.info(f"📊 Procesando {len(rows)} filas precisas")
            
            for i, row in enumerate(rows[:10]):  # Limitar a 10 para mejor precisión
                try:
                    row_text = safe_get_text(row)
                    
                    # Verificar que tiene contenido relevante
                    if len(row_text) < 20 or not any(keyword in row_text.lower() for keyword in ['remate', '20']):
                        continue
                    
                    # Buscar número de remate
                    numero_match = re.search(r'Remate\s+N°?\s*(\d+)', row_text, re.IGNORECASE)
                    if not numero_match:
                        numero_match = re.search(r'(?:^|\s)(\d{4,6})(?:\s|$)', row_text)
                    
                    if numero_match:
                        numero_remate = numero_match.group(1)
                        
                        # Extraer celdas individuales para mayor precisión
                        cells = row.find_elements(By.XPATH, ".//td")
                        cell_texts = [safe_get_text(cell) for cell in cells if safe_get_text(cell)]
                        
                        # Extraer información precisa
                        precio_texto, precio_numerico, moneda = self.extract_price_from_cells(cell_texts)
                        if not precio_texto:
                            precio_texto, precio_numerico, moneda = extract_price_info(row_text)
                        
                        fecha = self.extract_date_from_cells(cell_texts)
                        if not fecha:
                            fecha_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', row_text)
                            fecha = fecha_match.group(1) if fecha_match else ""
                        
                        ubicacion = self.extract_location_from_cells(cell_texts)
                        if not ubicacion:
                            ubicacion = self.extract_location_from_text(row_text)
                        
                        remate_data = {
                            'numero_remate': numero_remate,
                            'titulo_card': f"Remate N° {numero_remate}",
                            'ubicacion_corta': ubicacion,
                            'fecha_presentacion_oferta': fecha,
                            'precio_base_texto': precio_texto,
                            'precio_base_numerico': precio_numerico,
                            'moneda': moneda,
                            'button_index': i,
                            'cell_data': cell_texts,
                            'extraction_method': 'rows_structured_precise'
                        }
                        
                        remates.append(remate_data)
                        logger.info(f"✅ Remate fila preciso {numero_remate}: {ubicacion}")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Error procesando fila {i}: {e}")
                    continue
            
            return remates
            
        except Exception as e:
            logger.error(f"❌ Error en extracción de filas precisas: {e}")
            return []
    
    def extract_price_from_cells(self, cell_texts):
        """Extraer precio de celdas específicas"""
        precio_texto, precio_numerico, moneda = "", 0.0, ""
        
        for cell_text in cell_texts:
            if precio_texto:  # Ya encontró precio
                break
                
            # Buscar patrones de precio en esta celda específica
            price_patterns = [
                r'(S/\.|\$|USD)\s*([\d,]+\.?\d*)',
                r'([\d,]+\.?\d*)\s*(SOLES|DOLARES|USD)',
                r'Precio[:\s]*(S/\.|\$|USD)?\s*([\d,]+\.?\d*)',
                r'Base[:\s]*(S/\.|\$|USD)?\s*([\d,]+\.?\d*)'
            ]
            
            for pattern in price_patterns:
                match = re.search(pattern, cell_text, re.IGNORECASE)
                if match:
                    try:
                        if len(match.groups()) == 2:
                            g1, g2 = match.groups()
                            if g1 and any(char.isdigit() for char in g1):
                                amount_str = g1.replace(',', '')
                                currency = g2
                            else:
                                amount_str = g2.replace(',', '')
                                currency = g1
                            
                            amount = float(amount_str)
                            currency = "USD" if currency in ["$", "USD", "DOLARES"] else "S/."
                            
                            precio_texto = f"{currency} {match.group(2) if any(char.isdigit() for char in match.group(2)) else match.group(1)}"
                            precio_numerico = amount
                            moneda = currency
                            break
                    except:
                        continue
        
        return precio_texto, precio_numerico, moneda
    
    def extract_date_from_cells(self, cell_texts):
        """Extraer fecha de celdas específicas"""
        for cell_text in cell_texts:
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', cell_text)
            if date_match:
                return date_match.group(1)
        return ""
    
    def extract_location_from_cells(self, cell_texts):
        """Extraer ubicación de celdas específicas"""
        ciudades = ['LIMA', 'CALLAO', 'AREQUIPA', 'CUSCO', 'TRUJILLO', 'PIURA', 'CHICLAYO', 'HUANCAYO']
        
        for cell_text in cell_texts:
            cell_upper = cell_text.upper()
            for ciudad in ciudades:
                if ciudad in cell_upper:
                    return ciudad
        return ""
    
    def extract_location_from_text(self, text):
        """Extraer ubicación de texto general"""
        ciudades = ['LIMA', 'CALLAO', 'AREQUIPA', 'CUSCO', 'TRUJILLO', 'PIURA', 'CHICLAYO', 'HUANCAYO']
        text_upper = text.upper()
        for ciudad in ciudades:
            if ciudad in text_upper:
                return ciudad
        return ""
    
    def extract_from_page_text(self):
        """Fallback: extraer desde texto de página"""
        remates = []
        try:
            logger.info("🔄 Extracción fallback desde texto...")
            
            body = self.driver.find_element(By.TAG_NAME, "body")
            body_text = safe_get_text(body)
            
            # Buscar números de remate
            remate_numbers = re.findall(r'Remate\s+N°?\s*(\d+)', body_text, re.IGNORECASE)
            unique_numbers = list(set(remate_numbers))[:10]  # Máximo 10
            
            logger.info(f"🔍 Números encontrados en texto: {len(unique_numbers)}")
            
            for i, numero in enumerate(unique_numbers):
                try:
                    # Buscar contexto más amplio
                    context = self.extract_enhanced_context(body_text, numero)
                    
                    precio_texto, precio_numerico, moneda = extract_price_info(context)
                    fecha_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', context)
                    fecha = fecha_match.group(1) if fecha_match else ""
                    ubicacion = self.extract_location_from_text(context)
                    
                    remate_data = {
                        'numero_remate': numero,
                        'titulo_card': f"Remate N° {numero}",
                        'ubicacion_corta': ubicacion,
                        'fecha_presentacion_oferta': fecha,
                        'precio_base_texto': precio_texto,
                        'precio_base_numerico': precio_numerico,
                        'moneda': moneda,
                        'button_index': i,
                        'extraction_method': 'text_fallback_enhanced'
                    }
                    
                    remates.append(remate_data)
                    logger.info(f"✅ Remate texto mejorado {numero}: {ubicacion}")
                    
                except Exception as e:
                    continue
                    
            return remates
            
        except Exception as e:
            logger.error(f"❌ Error en extracción de texto: {e}")
            return []
    
    def extract_enhanced_context(self, body_text, numero):
        """Extraer contexto mejorado para un número de remate"""
        try:
            # Estrategia 1: Buscar patrón completo
            pattern = rf'Remate\s+N°?\s*{numero}.*?(?=Remate\s+N°?|\n\n|\Z)'
            match = re.search(pattern, body_text, re.IGNORECASE | re.DOTALL)
            if match and len(match.group(0)) > 50:
                return match.group(0)
            
            # Estrategia 2: Buscar líneas alrededor
            lines = body_text.split('\n')
            for i, line in enumerate(lines):
                if numero in line:
                    start = max(0, i - 5)
                    end = min(len(lines), i + 6)
                    return ' '.join(lines[start:end])
            
            return ""
            
        except Exception as e:
            return ""
    
    def navigate_to_detail_precision(self, remate_data):
        """Navegar al detalle con precisión"""
        try:
            numero_remate = remate_data.get('numero_remate')
            logger.info(f"🔍 Navegando al detalle (precisión): {numero_remate}")
            
            initial_url = self.driver.current_url
            
            # Re-buscar botones con más selectores específicos
            button_selectors = [
                f"//button[contains(@class, 'ui-button') and contains(@onclick, '{numero_remate}')]",
                f"//a[contains(@href, '{numero_remate}')]",
                "//button[contains(@class, 'ui-button')]",
                "//span[contains(@class, 'ui-button')]",
                "//a[contains(@class, 'ui-button')]",
                "//input[@type='submit' and contains(@value, 'Detalle')]",
                "//button[contains(text(), 'Detalle') or contains(text(), 'Ver')]"
            ]
            
            for selector in button_selectors:
                try:
                    buttons = self.driver.find_elements(By.XPATH, selector)
                    if buttons:
                        logger.info(f"🎯 Encontrados {len(buttons)} botones con: {selector}")
                        
                        # Probar botones específicos
                        button_index = remate_data.get('button_index', 0)
                        indices_to_try = [button_index] + list(range(min(len(buttons), 5)))
                        
                        for idx in indices_to_try:
                            if idx >= len(buttons):
                                continue
                            
                            try:
                                button = buttons[idx]
                                if button.is_displayed() and button.is_enabled():
                                    logger.info(f"🎯 Probando botón índice {idx}")
                                    
                                    # Click mejorado
                                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                    time.sleep(1)
                                    self.driver.execute_script("arguments[0].click();", button)
                                    
                                    # Esperar cambio con más tiempo
                                    if self.wait_for_change_precision(initial_url):
                                        logger.info(f"✅ Éxito navegación precisa con botón {idx}")
                                        return True
                                    else:
                                        # Regresar si no funcionó
                                        if self.driver.current_url != initial_url:
                                            self.driver.get(self.main_page_url)
                                            wait_for_primefaces_ready(self.driver)
                                            time.sleep(2)
                                
                            except Exception as e:
                                continue
                        
                        break  # Si encontró botones con este selector, no probar otros
                        
                except Exception as e:
                    continue
            
            logger.warning(f"⚠️ No se pudo navegar con precisión: {numero_remate}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error en navegación de precisión: {e}")
            return False
    
    def wait_for_change_precision(self, initial_url, timeout=15):
        """Esperar cambio con validación de precisión"""
        try:
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                current_url = self.driver.current_url
                
                # URL cambió
                if current_url != initial_url:
                    time.sleep(3)  # Más tiempo para carga completa
                    wait_for_primefaces_ready(self.driver, timeout=15)
                    
                    # Verificar que realmente cargó contenido de detalle
                    if self.validate_detail_content():
                        return True
                    else:
                        logger.warning("⚠️ URL cambió pero sin contenido de detalle válido")
                        return False
                
                # Contenido apareció sin cambio de URL (modal/ajax)
                if self.validate_detail_content():
                    return True
                
                time.sleep(0.5)
            
            return False
            
        except:
            return False
    
    def validate_detail_content(self):
        """Validar que realmente hay contenido de detalle"""
        try:
            body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body")).lower()
            
            # Indicadores más específicos
            strong_indicators = [
                'expediente', 'n° expediente', 'numero de expediente',
                'distrito judicial', 'órgano jurisdiccional',
                'juez', 'magistrado', 'tasación'
            ]
            
            weak_indicators = [
                'precio base', 'convocatoria', 'remate',
                'partida registral', 'cronograma'
            ]
            
            strong_count = sum(1 for indicator in strong_indicators if indicator in body_text)
            weak_count = sum(1 for indicator in weak_indicators if indicator in body_text)
            
            # Debe tener al menos 2 indicadores fuertes O 4 débiles
            is_valid = strong_count >= 2 or weak_count >= 4
            
            if is_valid:
                logger.info(f"✅ Contenido validado: {strong_count} fuertes, {weak_count} débiles")
            else:
                logger.warning(f"⚠️ Contenido insuficiente: {strong_count} fuertes, {weak_count} débiles")
            
            return is_valid
            
        except Exception as e:
            logger.warning(f"⚠️ Error validando contenido: {e}")
            return False
    
    def extract_detail_precision(self):
        """Extraer detalle con máxima precisión"""
        try:
            logger.info("📋 Extrayendo detalle (máxima precisión)...")
            
            # Esperar que todo cargue completamente
            wait_for_primefaces_ready(self.driver, timeout=15)
            time.sleep(2)
            
            # Obtener texto completo
            body_text = ""
            try:
                body = self.driver.find_element(By.TAG_NAME, "body")
                body_text = safe_get_text(body)
                logger.info(f"📄 Contenido detalle: {len(body_text)} caracteres")
            except:
                return {'error': 'No se pudo obtener texto del detalle'}
            
            # Intentar extracción estructurada primero
            detail_info = self.extract_fields_structured(body_text)
            
            # Si no funciona, usar extracción de texto mejorada
            if not any(detail_info.values()):
                detail_info = self.extract_fields_text_enhanced(body_text)
            
            # Agregar metadatos
            detail_info.update({
                'extraction_timestamp': datetime.now().isoformat(),
                'source_url': self.driver.current_url,
                'content_length': len(body_text),
                'extraction_quality': self.assess_extraction_quality(detail_info)
            })
            
            self.update_field_success_stats(detail_info)
            
            logger.info(f"✅ Detalle precisión extraído - Calidad: {detail_info.get('extraction_quality')}")
            return detail_info
            
        except Exception as e:
            logger.error(f"❌ Error extrayendo detalle de precisión: {e}")
            return {
                'error': str(e),
                'extraction_timestamp': datetime.now().isoformat()
            }
    
    def extract_fields_structured(self, body_text):
        """Extraer campos usando múltiples estrategias estructuradas"""
        detail_info = {}
        
        # Estrategia 1: Buscar tablas de información
        try:
            tables = self.driver.find_elements(By.XPATH, "//table")
            for table in tables:
                table_text = safe_get_text(table)
                if any(keyword in table_text.lower() for keyword in ['expediente', 'distrito', 'juez']):
                    detail_info.update(self.extract_from_info_table(table))
                    break
        except:
            pass
        
        # Estrategia 2: Buscar divs con clases específicas
        try:
            info_divs = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'ui-panel') or contains(@class, 'info') or contains(@class, 'detail')]")
            for div in info_divs:
                div_text = safe_get_text(div)
                if len(div_text) > 100:
                    detail_info.update(self.extract_from_info_div(div_text))
                    break
        except:
            pass
        
        # Estrategia 3: Buscar labels y spans
        try:
            labels = self.driver.find_elements(By.XPATH, "//label | //span[@class] | //strong")
            for label in labels:
                label_text = safe_get_text(label).lower()
                if any(keyword in label_text for keyword in ['expediente', 'distrito', 'juez', 'precio']):
                    sibling_text = self.get_sibling_text(label)
                    if sibling_text:
                        field_name = self.map_field_name(label_text)
                        if field_name:
                            detail_info[field_name] = sibling_text[:200]  # Limitar longitud
        except:
            pass
        
        return detail_info
    
    def extract_from_info_table(self, table):
        """Extraer información de tabla estructurada"""
        info = {}
        try:
            rows = table.find_elements(By.XPATH, ".//tr")
            for row in rows:
                cells = row.find_elements(By.XPATH, ".//td | .//th")
                if len(cells) >= 2:
                    label = safe_get_text(cells[0]).lower().strip()
                    value = safe_get_text(cells[1]).strip()
                    
                    field_name = self.map_field_name(label)
                    if field_name and value and len(value) > 3:
                        info[field_name] = value[:200]
        except:
            pass
        
        return info
    
    def extract_from_info_div(self, div_text):
        """Extraer información de div de información"""
        info = {}
        try:
            # Dividir por líneas y buscar patrones
            lines = div_text.split('\n')
            for line in lines:
                line = line.strip()
                if ':' in line and len(line) > 10:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        label = parts[0].strip().lower()
                        value = parts[1].strip()
                        
                        field_name = self.map_field_name(label)
                        if field_name and value and len(value) > 3:
                            info[field_name] = value[:200]
        except:
            pass
        
        return info
    
    def get_sibling_text(self, element):
        """Obtener texto de elemento hermano o siguiente"""
        try:
            # Buscar en siguiente elemento hermano
            next_sibling = element.find_element(By.XPATH, "./following-sibling::*[1]")
            text = safe_get_text(next_sibling)
            if text and len(text) > 3:
                return text
            
            # Buscar en padre siguiente
            parent = element.find_element(By.XPATH, "./..")
            parent_text = safe_get_text(parent)
            element_text = safe_get_text(element)
            if parent_text and element_text in parent_text:
                remaining = parent_text.replace(element_text, '').strip()
                if len(remaining) > 3:
                    return remaining[:200]
            
            return ""
        except:
            return ""
    
    def map_field_name(self, label_text):
        """Mapear texto de label a nombre de campo"""
        mappings = {
            'expediente': 'expediente',
            'n° expediente': 'expediente', 
            'numero expediente': 'expediente',
            'distrito judicial': 'distrito_judicial',
            'organo jurisdiccional': 'organo_jurisdiccional',
            'órgano jurisdiccional': 'organo_jurisdiccional',
            'juez': 'juez',
            'magistrado': 'juez',
            'precio base': 'precio_base',
            'tasacion': 'tasacion',
            'tasación': 'tasacion',
            'convocatoria': 'convocatoria',
            'descripcion': 'descripcion',
            'descripción': 'descripcion'
        }
        
        for key, field in mappings.items():
            if key in label_text:
                return field
        
        return None
    
    def extract_fields_text_enhanced(self, body_text):
        """Extracción mejorada de campos desde texto"""
        detail_info = {}
        
        # Limpiar y normalizar texto
        clean_text = re.sub(r'\s+', ' ', body_text)
        clean_text = re.sub(r'[^\w\s\-.:/()\u00C0-\u017F]', ' ', clean_text)
        
        field_patterns = {
            'expediente': [
                r'Expediente[:\s]*([A-Z0-9\-]+(?:\-\d+){3,})',
                r'N°?\s*Expediente[:\s]*([A-Z0-9\-]+(?:\-\d+){3,})',
                r'Exp[^a-z]*([A-Z0-9\-]+(?:\-\d+){3,})',
                r'(\d{4,5}\-\d{4}\-\d\-\d{4}\-[A-Z]{2}\-[A-Z]{2}\-\d{2})'
            ],
            'distrito_judicial': [
                r'Distrito\s+Judicial[:\s]*([A-ZÁÉÍÓÚÑ\s]+?)(?=\n|Órgano|Juez|$)',
                r'Distrito[:\s]*([A-ZÁÉÍÓÚÑ\s]{3,30}?)(?=\n|[A-Z]{3,}|$)'
            ],
            'organo_jurisdiccional': [
                r'Órgano\s+Jurisdiccional[:\s]*([^:\n]+?)(?=\n|Instancia|Juez|$)',
                r'Órgano\s+Jurisdisccional[:\s]*([^:\n]+?)(?=\n|Instancia|Juez|$)',
                r'Juzgado[:\s]*([^:\n]+?)(?=\n|Instancia|Juez|$)'
            ],
            'juez': [
                r'Juez[:\s]*([A-ZÁÉÍÓÚÑ\s]+?)(?=\n|Especialista|Materia|$)',
                r'Magistrado[:\s]*([A-ZÁÉÍÓÚÑ\s]+?)(?=\n|Especialista|$)'
            ],
            'precio_base': [
                r'Precio\s+Base[:\s]*([USD\$S/\.\s\d,]+\.?\d*)',
                r'Base[:\s]*([USD\$S/\.\s\d,]+\.?\d*)'
            ],
            'tasacion': [
                r'Tasación[:\s]*([USD\$S/\.\s\d,]+\.?\d*)',
                r'Tasacion[:\s]*([USD\$S/\.\s\d,]+\.?\d*)'
            ],
            'convocatoria': [
                r'Convocatoria[:\s]*([A-Z\s]+?)(?=\n|Tasación|Precio|$)'
            ]
        }
        
        for field, patterns in field_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, clean_text, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    # Limpiar y validar valor
                    value = re.sub(r'^[\s:]+', '', value)
                    value = re.sub(r'\s+', ' ', value)
                    
                    if 3 < len(value) < 200 and value not in ['', 'N/A', '-']:
                        detail_info[field] = value
                        break
        
        return detail_info
    
    def assess_extraction_quality(self, detail_info):
        """Evaluar calidad de extracción"""
        important_fields = ['expediente', 'distrito_judicial', 'organo_jurisdiccional', 'juez']
        filled_important = sum(1 for field in important_fields if detail_info.get(field))
        
        total_fields = len([v for v in detail_info.values() if v and v != ''])
        
        if filled_important >= 3:
            return 'alta'
        elif filled_important >= 2:
            return 'media'
        elif total_fields >= 3:
            return 'baja'
        else:
            return 'muy_baja'
    
    def update_field_success_stats(self, detail_info):
        """Actualizar estadísticas de éxito por campo"""
        fields = ['expediente', 'distrito_judicial', 'organo_jurisdiccional', 'juez', 'precio_base', 'tasacion']
        
        for field in fields:
            if field not in self.stats['field_extraction_success']:
                self.stats['field_extraction_success'][field] = 0
            
            if detail_info.get(field):
                self.stats['field_extraction_success'][field] += 1
    
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
        """Ejecutar scraping con máxima precisión"""
        try:
            logger.info("🚀 Iniciando REMAJU Scraper de Alta Precisión")
            
            if not self.setup():
                return self.create_error_result("Error en configuración")
            
            if not self.navigate_to_main_page():
                return self.create_error_result("Error navegando a página principal")
            
            # Extraer remates con precisión
            remates = self.extract_remates_precision()
            
            if not remates:
                return self.create_error_result("No se encontraron remates")
            
            # Procesar detalles con precisión
            detailed_remates = []
            max_details = min(MAX_DETAILS, len(remates))
            
            logger.info(f"📊 Procesando detalles de alta precisión: {max_details}/{len(remates)}")
            
            for i in range(max_details):
                try:
                    remate = remates[i]
                    numero_remate = remate.get('numero_remate')
                    
                    logger.info(f"🎯 Procesando precisión {i+1}/{max_details}: {numero_remate}")
                    
                    if self.navigate_to_detail_precision(remate):
                        detail_info = self.extract_detail_precision()
                        
                        complete_remate = {
                            'numero_remate': numero_remate,
                            'basic_info': remate,
                            'detalle': detail_info,
                            'extraction_success': True
                        }
                        
                        detailed_remates.append(complete_remate)
                        self.stats['remates_with_details'] += 1
                        
                        logger.info(f"✅ Detalle precisión extraído: {numero_remate}")
                    else:
                        failed_remate = {
                            'numero_remate': numero_remate,
                            'basic_info': remate,
                            'detalle': {'error': 'No se pudo acceder al detalle con precisión'},
                            'extraction_success': False
                        }
                        detailed_remates.append(failed_remate)
                        logger.warning(f"⚠️ Sin detalle precisión: {numero_remate}")
                    
                    # Regresar para siguiente con más tiempo
                    if i < max_details - 1:
                        try:
                            self.driver.get(self.main_page_url)
                            wait_for_primefaces_ready(self.driver, timeout=30)
                            time.sleep(3)
                        except:
                            pass
                    
                except Exception as e:
                    logger.error(f"❌ Error procesando precisión {i}: {e}")
                    self.stats['errors'] += 1
                    continue
            
            # Crear resultado final
            result = {
                'status': 'success',
                'timestamp': datetime.now().isoformat(),
                'sistema': 'REMAJU_PRECISION',
                'fuente': MAIN_URL,
                'estadisticas': self.generate_stats(),
                'total_remates_encontrados': len(remates),
                'remates_procesados': len(detailed_remates),
                'technology_detected': 'JSF + PrimeFaces (Precisión)',
                'precision_metrics': self.generate_precision_metrics(),
                'remates': detailed_remates
            }
            
            # Guardar resultado
            if self.save_result(result):
                logger.info(f"🎉 Extracción de precisión completada: {len(detailed_remates)} procesados")
                return result
            else:
                return self.create_error_result("Error guardando resultado")
            
        except Exception as e:
            logger.error(f"❌ Error en ejecución de precisión: {e}")
            return self.create_error_result(str(e))
        
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("🔒 Driver cerrado")
    
    def generate_precision_metrics(self):
        """Generar métricas de precisión"""
        total_attempts = self.stats['remates_with_details']
        if total_attempts == 0:
            return {}
        
        field_success_rates = {}
        for field, successes in self.stats['field_extraction_success'].items():
            field_success_rates[field] = round((successes / total_attempts) * 100, 2)
        
        return {
            'extraction_precision_errors': self.stats['extraction_precision_errors'],
            'field_success_rates': field_success_rates,
            'overall_precision_score': round(sum(field_success_rates.values()) / len(field_success_rates), 2) if field_success_rates else 0
        }
    
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
    """Función principal de alta precisión"""
    try:
        logger.info("🚀 REMAJU Scraper de Alta Precisión")
        
        scraper = REMAJUScraperPrecision()
        resultado = scraper.run()
        
        if resultado['status'] == 'success':
            stats = resultado['estadisticas']
            precision_metrics = resultado.get('precision_metrics', {})
            
            logger.info(f"🎉 ÉXITO DE ALTA PRECISIÓN")
            logger.info(f"📊 {stats['total_remates_encontrados']} remates encontrados")
            logger.info(f"✅ {stats['remates_con_detalle_exitoso']} con detalle extraído")
            logger.info(f"🎯 Score de precisión: {precision_metrics.get('overall_precision_score', 'N/A')}")
            logger.info(f"⏱️ Duración: {stats['duracion_segundos']} segundos")
            
            print(f"SUCCESS: {stats['total_remates_encontrados']} remates, {stats['remates_con_detalle_exitoso']} detalles de precisión")
            return 0
        else:
            logger.error(f"❌ ERROR DE PRECISIÓN: {resultado['error_message']}")
            print(f"ERROR: {resultado['error_message']}")
            return 1
        
    except Exception as e:
        logger.error(f"❌ Error crítico de precisión: {e}")
        
        # Crear archivo de error mínimo
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
