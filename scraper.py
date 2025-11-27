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
from selenium.common.exceptions import TimeoutException, JavascriptException
from selenium.webdriver.common.action_chains import ActionChains

# Configuración global
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://remaju.pj.gob.pe"
MAIN_URL = f"{BASE_URL}/remaju/pages/publico/remateExterno.xhtml"
MAX_DETAILS = int(os.environ.get('MAX_DETAILS', '3'))
HEADLESS = os.environ.get('HEADLESS', 'false').lower() == 'true'

class PrimeFacesWaitConditions:
    """Condiciones de espera específicas para PrimeFaces"""
    
    @staticmethod
    def primefaces_ajax_complete(driver):
        """Verificar que PrimeFaces haya completado todas las requests AJAX"""
        try:
            return driver.execute_script("""
                return (typeof window.PrimeFaces !== 'undefined') 
                    ? window.PrimeFaces.ajax.Queue.isEmpty() 
                    : true;
            """)
        except JavascriptException:
            return True
    
    @staticmethod 
    def jquery_ajax_complete(driver):
        """Verificar que jQuery haya completado todas las requests AJAX"""
        try:
            return driver.execute_script("""
                return (typeof window.jQuery !== 'undefined') 
                    ? (jQuery.active === 0) 
                    : true;
            """)
        except JavascriptException:
            return True
    
    @staticmethod
    def document_ready_complete(driver):
        """Verificar que el document esté completamente cargado"""
        try:
            return driver.execute_script("return document.readyState") == "complete"
        except JavascriptException:
            return True
    
    @staticmethod
    def all_ajax_complete(driver):
        """Verificar que todo AJAX esté completo"""
        return (PrimeFacesWaitConditions.primefaces_ajax_complete(driver) and 
                PrimeFacesWaitConditions.jquery_ajax_complete(driver) and
                PrimeFacesWaitConditions.document_ready_complete(driver))

def create_chrome_driver():
    """Configurar driver Chrome optimizado para JSF/PrimeFaces"""
    try:
        chrome_options = Options()
        if HEADLESS:
            chrome_options.add_argument("--headless=new")
        
        # Configuración base
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage") 
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # User agent realista
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Optimizaciones para JavaScript
        chrome_options.add_argument("--enable-javascript")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Habilitar logging de performance para debug
        caps = {
            'goog:loggingPrefs': {'performance': 'ALL', 'browser': 'ALL'}
        }
        chrome_options.set_capability('goog:loggingPrefs', caps['goog:loggingPrefs'])
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(120)  # Timeout más largo
        driver.implicitly_wait(15)  # Espera implícita para elementos
        
        # Ejecutar script anti-detección
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver
    except Exception as e:
        logger.error(f"Error configurando driver: {e}")
        return None

def wait_for_primefaces_ready(driver, timeout=30):
    """Esperar que PrimeFaces esté completamente cargado y listo"""
    try:
        logger.info("⏳ Esperando que PrimeFaces esté listo...")
        
        # Esperar que PrimeFaces esté definido
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return typeof window.PrimeFaces !== 'undefined'")
        )
        
        # Esperar que no haya AJAX activo
        WebDriverWait(driver, timeout).until(
            lambda d: PrimeFacesWaitConditions.all_ajax_complete(d)
        )
        
        # Espera adicional para estabilización
        time.sleep(3)
        
        logger.info("✅ PrimeFaces listo")
        return True
        
    except TimeoutException:
        logger.warning("⚠️ Timeout esperando PrimeFaces, continuando...")
        return False
    except Exception as e:
        logger.warning(f"⚠️ Error esperando PrimeFaces: {e}")
        return False

def safe_find_element(driver, by, value, timeout=15, optional=False):
    """Buscar elemento de forma segura con timeout extendido"""
    try:
        return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))
    except TimeoutException:
        if not optional:
            logger.warning(f"Elemento no encontrado: {value}")
        return None

def safe_get_text(element, default=""):
    """Obtener texto limpio de elemento"""
    try:
        if element:
            text = element.get_attribute('textContent') or element.text or default
            return ' '.join(text.strip().split())
        return default
    except:
        return default

def extract_price_info(text):
    """Extraer precio, monto y moneda de texto"""
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
            if currency_text in ["$", "USD", "DOLARES"]:
                currency = "USD"
            else:
                currency = "S/."
            
            amount_str = match.group(amount_group).replace(',', '')
            try:
                amount = float(amount_str)
                return f"{currency} {match.group(amount_group)}", amount, currency
            except:
                return text, 0.0, currency
    
    return text, 0.0, ""

class REMAJUPrimeFacesScraper:
    """Scraper optimizado para REMAJU usando JSF/PrimeFaces"""
    
    def __init__(self):
        self.driver = None
        self.main_page_url = ""
        self.performance_logs = []
        self.stats = {
            'start_time': datetime.now(),
            'total_remates': 0,
            'remates_with_details': 0,
            'errors': 0,
            'ajax_calls_detected': 0
        }
    
    def setup(self):
        """Configurar scraper"""
        try:
            self.driver = create_chrome_driver()
            if not self.driver:
                return False
            logger.info("✅ Driver configurado para JSF/PrimeFaces")
            return True
        except Exception as e:
            logger.error(f"❌ Error en setup: {e}")
            return False
    
    def navigate_to_main_page(self):
        """Navegar a página principal con manejo específico de PrimeFaces"""
        try:
            logger.info("🌐 Navegando a REMAJU (JSF/PrimeFaces)...")
            self.driver.get(MAIN_URL)
            
            # Esperar carga inicial del DOM
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Esperar que PrimeFaces esté listo
            wait_for_primefaces_ready(self.driver, timeout=40)
            
            self.main_page_url = self.driver.current_url
            logger.info(f"✅ Página JSF cargada: {self.main_page_url}")
            
            # Analizar logs de performance para debug
            self.analyze_performance_logs()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error navegando: {e}")
            return False
    
    def analyze_performance_logs(self):
        """Analizar logs de performance para detectar AJAX calls"""
        try:
            logs = self.driver.get_log('performance')
            ajax_calls = 0
            
            for log in logs:
                message = json.loads(log['message'])
                if message['message']['method'] == 'Network.requestWillBeSent':
                    url = message['message']['params'].get('request', {}).get('url', '')
                    if any(keyword in url.lower() for keyword in ['ajax', 'jsf', 'primefaces', '.xhtml']):
                        ajax_calls += 1
            
            self.stats['ajax_calls_detected'] = ajax_calls
            logger.info(f"🔍 AJAX calls detectadas: {ajax_calls}")
            
        except Exception as e:
            logger.warning(f"⚠️ Error analizando performance logs: {e}")
    
    def wait_for_element_with_content(self, timeout=20):
        """Esperar elementos con contenido específico para PrimeFaces"""
        try:
            # Estrategias específicas para componentes PrimeFaces
            primefaces_selectors = [
                # DataTable components
                "//table[contains(@class, 'ui-datatable')]",
                "//div[contains(@class, 'ui-datatable')]",
                # Panel components  
                "//div[contains(@class, 'ui-panel')]",
                "//div[contains(@class, 'ui-fieldset')]",
                # Form components
                "//form[contains(@class, 'ui-')]",
                # Button components
                "//button[contains(@class, 'ui-button')]",
                "//span[contains(@class, 'ui-button')]"
            ]
            
            logger.info("🔍 Buscando componentes PrimeFaces...")
            
            for selector in primefaces_selectors:
                try:
                    elements = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_all_elements_located((By.XPATH, selector))
                    )
                    if elements:
                        logger.info(f"✅ Encontrados {len(elements)} elementos: {selector}")
                        return True
                except TimeoutException:
                    continue
            
            logger.warning("⚠️ No se encontraron componentes PrimeFaces estándar")
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ Error esperando elementos PrimeFaces: {e}")
            return False
    
    def extract_remates_primefaces(self):
        """Extracción específica para componentes PrimeFaces"""
        remates = []
        try:
            logger.info("📋 Extrayendo remates con método PrimeFaces...")
            
            # Esperar componentes PrimeFaces
            self.wait_for_element_with_content()
            
            # Estrategia 1: Buscar en DataTables de PrimeFaces
            datatable_selectors = [
                "//table[contains(@class, 'ui-datatable')]//tbody//tr",
                "//div[contains(@class, 'ui-datatable')]//tbody//tr",
                "//table//tbody//tr[td[contains(text(), 'Remate')]]"
            ]
            
            for selector in datatable_selectors:
                try:
                    rows = self.driver.find_elements(By.XPATH, selector)
                    if rows:
                        logger.info(f"🎯 Encontradas {len(rows)} filas en tabla: {selector}")
                        remates.extend(self.extract_from_table_rows(rows))
                        if remates:
                            break
                except:
                    continue
            
            # Estrategia 2: Buscar en paneles/cards de PrimeFaces
            if not remates:
                panel_selectors = [
                    "//div[contains(@class, 'ui-panel')]",
                    "//div[contains(@class, 'ui-fieldset')]",
                    "//div[contains(@class, 'ui-widget')]"
                ]
                
                for selector in panel_selectors:
                    try:
                        panels = self.driver.find_elements(By.XPATH, selector)
                        for panel in panels:
                            panel_text = safe_get_text(panel)
                            if 'remate' in panel_text.lower():
                                remates.extend(self.extract_from_panel(panel))
                    except:
                        continue
            
            # Estrategia 3: Buscar en toda la página después de AJAX completo
            if not remates:
                logger.info("🔄 Esperando AJAX adicional y extrayendo de página completa...")
                time.sleep(5)  # Espera adicional
                wait_for_primefaces_ready(self.driver, timeout=20)
                remates = self.extract_from_full_page_primefaces()
            
            self.stats['total_remates'] = len(remates)
            logger.info(f"📊 Total extraído con PrimeFaces: {len(remates)} remates")
            
            # Guardar debug info
            self.save_debug_info()
            
            return remates
            
        except Exception as e:
            logger.error(f"❌ Error extrayendo remates PrimeFaces: {e}")
            return self.extract_from_full_page_primefaces()  # Fallback
    
    def extract_from_table_rows(self, rows):
        """Extraer remates desde filas de tabla PrimeFaces"""
        remates = []
        try:
            for i, row in enumerate(rows[:20]):  # Máximo 20 filas
                try:
                    row_text = safe_get_text(row)
                    
                    # Buscar número de remate
                    numero_match = re.search(r'Remate\s+N°?\s*(\d+)', row_text, re.IGNORECASE)
                    if not numero_match:
                        numero_match = re.search(r'(\d{4,6})', row_text)  # Números de 4-6 dígitos
                    
                    if numero_match:
                        numero_remate = numero_match.group(1)
                        
                        # Extraer celdas de la fila
                        cells = row.find_elements(By.TAG_NAME, "td")
                        cell_texts = [safe_get_text(cell) for cell in cells]
                        
                        # Buscar botón de detalle en la fila
                        detail_button = None
                        button_selectors = [
                            ".//button[contains(@class, 'ui-button')]",
                            ".//span[contains(@class, 'ui-button')]",
                            ".//a[contains(@class, 'ui-button')]",
                            ".//button[contains(text(), 'Detalle')]",
                            ".//a[contains(text(), 'Detalle')]"
                        ]
                        
                        for btn_selector in button_selectors:
                            try:
                                detail_button = row.find_element(By.XPATH, btn_selector)
                                if detail_button.is_displayed() and detail_button.is_enabled():
                                    break
                            except:
                                detail_button = None
                                continue
                        
                        # Extraer información de las celdas
                        precio_texto, precio_numerico, moneda = "", 0.0, ""
                        ubicacion = ""
                        fecha = ""
                        
                        for cell_text in cell_texts:
                            if not precio_texto:
                                precio_texto, precio_numerico, moneda = extract_price_info(cell_text)
                            
                            if not fecha and re.search(r'\d{1,2}/\d{1,2}/\d{4}', cell_text):
                                fecha_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', cell_text)
                                fecha = fecha_match.group(1)
                            
                            if not ubicacion and any(ciudad in cell_text.upper() for ciudad in ['LIMA', 'CALLAO', 'AREQUIPA', 'CUSCO']):
                                for ciudad in ['LIMA', 'CALLAO', 'AREQUIPA', 'CUSCO', 'TRUJILLO']:
                                    if ciudad in cell_text.upper():
                                        ubicacion = ciudad
                                        break
                        
                        remate_data = {
                            'numero_remate': numero_remate,
                            'titulo_card': f"Remate N° {numero_remate}",
                            'ubicacion_corta': ubicacion,
                            'fecha_presentacion_oferta': fecha,
                            'precio_base_texto': precio_texto,
                            'precio_base_numerico': precio_numerico,
                            'moneda': moneda,
                            'cell_data': cell_texts,
                            'detail_button': detail_button,
                            'row_element': row,
                            'card_index': i,
                            'extraction_method': 'primefaces_table'
                        }
                        
                        remates.append(remate_data)
                        logger.info(f"✅ Remate tabla {numero_remate}: {ubicacion}")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Error procesando fila {i}: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"❌ Error extrayendo de filas: {e}")
        
        return remates
    
    def extract_from_panel(self, panel):
        """Extraer remate desde panel PrimeFaces"""
        remates = []
        try:
            panel_text = safe_get_text(panel)
            
            # Buscar número de remate
            numero_match = re.search(r'Remate\s+N°?\s*(\d+)', panel_text, re.IGNORECASE)
            if numero_match:
                numero_remate = numero_match.group(1)
                
                # Extraer información del panel
                precio_texto, precio_numerico, moneda = extract_price_info(panel_text)
                
                fecha_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', panel_text)
                fecha = fecha_match.group(1) if fecha_match else ""
                
                # Buscar botón de detalle en el panel
                detail_button = None
                try:
                    detail_button = panel.find_element(By.XPATH, ".//button[contains(@class, 'ui-button')] | .//a[contains(@class, 'ui-button')]")
                except:
                    pass
                
                remate_data = {
                    'numero_remate': numero_remate,
                    'titulo_card': f"Remate N° {numero_remate}",
                    'fecha_presentacion_oferta': fecha,
                    'precio_base_texto': precio_texto,
                    'precio_base_numerico': precio_numerico,
                    'moneda': moneda,
                    'detail_button': detail_button,
                    'panel_element': panel,
                    'extraction_method': 'primefaces_panel'
                }
                
                remates.append(remate_data)
                
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo de panel: {e}")
        
        return remates
    
    def extract_from_full_page_primefaces(self):
        """Fallback: extraer de página completa después de PrimeFaces"""
        remates = []
        try:
            logger.info("🔄 Extracción fallback desde página completa...")
            
            body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body"))
            
            # Buscar números de remate
            remate_numbers = re.findall(r'Remate\s+N°?\s*(\d+)', body_text, re.IGNORECASE)
            unique_numbers = list(set(remate_numbers))[:10]  # Máximo 10
            
            logger.info(f"🔍 Números únicos en página completa: {unique_numbers}")
            
            for i, numero in enumerate(unique_numbers):
                try:
                    # Buscar contexto del número
                    pattern = rf'Remate\s+N°?\s*{numero}.*?(?=Remate\s+N°?|\Z)'
                    context_match = re.search(pattern, body_text, re.IGNORECASE | re.DOTALL)
                    context = context_match.group(0) if context_match else ""
                    
                    if len(context) < 50:  # Si el contexto es muy pequeño, buscar más
                        # Buscar elementos que contengan el número
                        number_elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{numero}')]")
                        
                        best_context = ""
                        for element in number_elements[:3]:
                            try:
                                # Buscar contenedor padre con más información
                                current = element
                                for _ in range(4):
                                    try:
                                        parent = current.find_element(By.XPATH, "./..")
                                        parent_text = safe_get_text(parent)
                                        
                                        if len(parent_text) > len(best_context) and numero in parent_text:
                                            best_context = parent_text
                                        current = parent
                                    except:
                                        break
                            except:
                                continue
                        
                        context = best_context or context
                    
                    # Extraer información del contexto
                    precio_texto, precio_numerico, moneda = extract_price_info(context)
                    
                    fecha_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', context)
                    fecha = fecha_match.group(1) if fecha_match else ""
                    
                    # Determinar ubicación
                    ubicacion = ""
                    for ciudad in ['LIMA', 'CALLAO', 'AREQUIPA', 'CUSCO', 'TRUJILLO']:
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
                        'context_text': context[:500],
                        'card_index': i,
                        'extraction_method': 'fallback_fullpage'
                    }
                    
                    remates.append(remate_data)
                    logger.info(f"✅ Remate fallback {numero}: {ubicacion}")
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error procesando remate {numero}: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"❌ Error en extracción fallback: {e}")
        
        return remates
    
    def navigate_to_detail_primefaces(self, remate_data):
        """Navegación específica para botones PrimeFaces"""
        try:
            numero_remate = remate_data.get('numero_remate')
            logger.info(f"🔍 Navegando al detalle PrimeFaces: {numero_remate}")
            
            initial_url = self.driver.current_url
            
            # Estrategia 1: Botón específico PrimeFaces
            if remate_data.get('detail_button'):
                try:
                    button = remate_data['detail_button']
                    logger.info("🎯 Usando botón PrimeFaces específico")
                    
                    # Scroll al botón
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                    time.sleep(1)
                    
                    # Click con manejo de PrimeFaces
                    self.driver.execute_script("arguments[0].click();", button)
                    
                    # Esperar respuesta AJAX de PrimeFaces
                    if self.wait_for_primefaces_navigation():
                        logger.info("✅ Navegación PrimeFaces exitosa")
                        return True
                        
                except Exception as e:
                    logger.warning(f"⚠️ Error con botón PrimeFaces: {e}")
            
            # Estrategia 2: Buscar botones PrimeFaces globales
            try:
                logger.info("🎯 Buscando botones PrimeFaces globales")
                
                pf_button_selectors = [
                    "//button[contains(@class, 'ui-button')]",
                    "//span[contains(@class, 'ui-button')]",
                    "//a[contains(@class, 'ui-button')]",
                    "//input[contains(@class, 'ui-button')]"
                ]
                
                all_buttons = []
                for selector in pf_button_selectors:
                    try:
                        buttons = self.driver.find_elements(By.XPATH, selector)
                        for button in buttons:
                            if button.is_displayed() and button.is_enabled():
                                btn_text = safe_get_text(button).lower()
                                if any(keyword in btn_text for keyword in ['detalle', 'detail', 'ver', 'consultar']):
                                    all_buttons.append(button)
                    except:
                        continue
                
                logger.info(f"📊 Botones PrimeFaces relevantes: {len(all_buttons)}")
                
                # Probar botones por orden
                card_index = remate_data.get('card_index', 0)
                indices_to_try = [card_index] + list(range(len(all_buttons)))
                
                for idx in indices_to_try[:5]:
                    if idx >= len(all_buttons):
                        continue
                        
                    try:
                        button = all_buttons[idx]
                        logger.info(f"🎯 Probando botón PrimeFaces {idx}")
                        
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                        time.sleep(1)
                        self.driver.execute_script("arguments[0].click();", button)
                        
                        if self.wait_for_primefaces_navigation():
                            logger.info(f"✅ Éxito con botón PrimeFaces {idx}")
                            return True
                        else:
                            self.return_to_main_if_needed(initial_url)
                            
                    except Exception as e:
                        logger.warning(f"⚠️ Error con botón {idx}: {e}")
                        continue
                        
            except Exception as e:
                logger.warning(f"⚠️ Error buscando botones PrimeFaces: {e}")
            
            logger.error(f"❌ No se pudo navegar al detalle PrimeFaces: {numero_remate}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error navegando al detalle: {e}")
            return False
    
    def wait_for_primefaces_navigation(self, timeout=20):
        """Esperar navegación o respuesta AJAX de PrimeFaces"""
        try:
            initial_url = self.driver.current_url
            
            def check_primefaces_response():
                try:
                    # Verificar cambio de URL
                    current_url = self.driver.current_url  
                    if current_url != initial_url:
                        return True
                    
                    # Verificar contenido de detalle cargado via AJAX
                    body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body")).lower()
                    detail_indicators = [
                        'expediente', 'tasación', 'partida', 'distrito judicial',
                        'órgano jurisdiccional', 'cronograma', 'inmuebles',
                        'resolución', 'juez', 'materia', 'convocatoria'
                    ]
                    
                    has_detail_content = any(indicator in body_text for indicator in detail_indicators)
                    
                    # Verificar que PrimeFaces haya completado AJAX
                    ajax_complete = PrimeFacesWaitConditions.all_ajax_complete(self.driver)
                    
                    return has_detail_content and ajax_complete
                    
                except:
                    return False
            
            # Esperar respuesta
            start_time = time.time()
            while time.time() - start_time < timeout:
                if check_primefaces_response():
                    # Espera adicional para estabilización
                    time.sleep(2)
                    wait_for_primefaces_ready(self.driver, timeout=10)
                    return True
                time.sleep(0.5)
            
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ Error esperando navegación PrimeFaces: {e}")
            return False
    
    def return_to_main_if_needed(self, expected_url):
        """Regresar a página principal con manejo PrimeFaces"""
        try:
            current_url = self.driver.current_url
            if current_url != expected_url:
                logger.info("🔙 Regresando con manejo PrimeFaces...")
                
                # Buscar botón regresar PrimeFaces
                back_selectors = [
                    "//button[contains(@class, 'ui-button') and contains(translate(text(), 'REGRESAR', 'regresar'), 'regresar')]",
                    "//a[contains(@class, 'ui-button') and contains(translate(text(), 'REGRESAR', 'regresar'), 'regresar')]",
                    "//span[contains(@class, 'ui-button') and contains(translate(text(), 'VOLVER', 'volver'), 'volver')]"
                ]
                
                for selector in back_selectors:
                    try:
                        back_btn = safe_find_element(self.driver, By.XPATH, selector, timeout=5, optional=True)
                        if back_btn and back_btn.is_displayed():
                            self.driver.execute_script("arguments[0].click();", back_btn)
                            wait_for_primefaces_ready(self.driver, timeout=15)
                            return
                    except:
                        continue
                
                # Si no hay botón, navegar directamente
                self.driver.get(self.main_page_url)
                wait_for_primefaces_ready(self.driver, timeout=20)
                
        except Exception as e:
            logger.warning(f"⚠️ Error regresando: {e}")
    
    def extract_detail_primefaces(self):
        """Extraer detalle con manejo específico de PrimeFaces"""
        try:
            logger.info("📋 Extrayendo detalle PrimeFaces...")
            
            # Esperar que PrimeFaces complete la carga
            wait_for_primefaces_ready(self.driver, timeout=15)
            
            body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body"))
            
            # Extracción básica de campos
            detail_info = {
                'expediente': self.extract_field_value_primefaces(body_text, ['Expediente', 'N° Expediente']),
                'distrito_judicial': self.extract_field_value_primefaces(body_text, ['Distrito Judicial']),
                'organo_jurisdiccional': self.extract_field_value_primefaces(body_text, ['Órgano Jurisdiccional']),
                'juez': self.extract_field_value_primefaces(body_text, ['Juez']),
                'precio_base': self.extract_field_value_primefaces(body_text, ['Precio Base']),
                'tasacion': self.extract_field_value_primefaces(body_text, ['Tasación']),
                'convocatoria': self.extract_field_value_primefaces(body_text, ['Convocatoria']),
                'extraction_timestamp': datetime.now().isoformat(),
                'source_url': self.driver.current_url,
                'primefaces_components': self.detect_primefaces_components()
            }
            
            logger.info(f"✅ Detalle PrimeFaces extraído - Expediente: {detail_info.get('expediente') or 'N/A'}")
            return detail_info
            
        except Exception as e:
            logger.error(f"❌ Error extrayendo detalle PrimeFaces: {e}")
            return {
                'error': str(e),
                'extraction_timestamp': datetime.now().isoformat(),
                'source_url': self.driver.current_url if self.driver else 'unknown'
            }
    
    def extract_field_value_primefaces(self, text, field_labels):
        """Extraer valor de campo con manejo específico de PrimeFaces"""
        for label in field_labels:
            patterns = [
                rf'{re.escape(label)}\s*:?\s*([^\n\r]+)',
                rf'{re.escape(label)}\s*[:\-]\s*([^\n\r]+)',
                rf'<.*?>\s*{re.escape(label)}\s*<.*?>\s*([^<\n\r]+)'  # Dentro de tags HTML
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    value = re.sub(r'^[\s:]+', '', value)
                    if len(value) > 3:
                        return value
        return ""
    
    def detect_primefaces_components(self):
        """Detectar componentes PrimeFaces presentes"""
        try:
            components = []
            component_selectors = {
                'datatable': "//table[contains(@class, 'ui-datatable')]",
                'panel': "//div[contains(@class, 'ui-panel')]", 
                'fieldset': "//div[contains(@class, 'ui-fieldset')]",
                'button': "//button[contains(@class, 'ui-button')]",
                'tabs': "//div[contains(@class, 'ui-tabs')]",
                'dialog': "//div[contains(@class, 'ui-dialog')]"
            }
            
            for name, selector in component_selectors.items():
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements:
                        components.append({'component': name, 'count': len(elements)})
                except:
                    continue
            
            return components
            
        except Exception as e:
            logger.warning(f"⚠️ Error detectando componentes PrimeFaces: {e}")
            return []
    
    def save_debug_info(self):
        """Guardar información de debug"""
        try:
            debug_info = {
                'timestamp': datetime.now().isoformat(),
                'url': self.driver.current_url,
                'performance_stats': {
                    'ajax_calls_detected': self.stats['ajax_calls_detected'],
                    'page_load_time': (datetime.now() - self.stats['start_time']).total_seconds()
                },
                'primefaces_components': self.detect_primefaces_components(),
                'page_sample': safe_get_text(self.driver.find_element(By.TAG_NAME, "body"))[:2000]
            }
            
            with open('/home/claude/remaju_primefaces_debug.json', 'w', encoding='utf-8') as f:
                json.dump(debug_info, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.warning(f"⚠️ Error guardando debug: {e}")
    
    def run_extraction(self):
        """Ejecutar extracción completa optimizada para PrimeFaces"""
        try:
            logger.info("🚀 Iniciando extracción REMAJU PrimeFaces")
            
            if not self.setup():
                return self.create_error_result("Error en configuración PrimeFaces")
            
            if not self.navigate_to_main_page():
                return self.create_error_result("Error navegando a página PrimeFaces")
            
            # Extraer remates con método PrimeFaces
            remates = self.extract_remates_primefaces()
            
            if not remates:
                return self.create_error_result("No se encontraron remates con método PrimeFaces")
            
            # Extraer detalles
            detailed_remates = []
            max_details = min(MAX_DETAILS, len(remates))
            
            logger.info(f"📊 Procesando detalles PrimeFaces: {max_details}/{len(remates)}")
            
            for i in range(max_details):
                try:
                    remate = remates[i]
                    numero_remate = remate.get('numero_remate')
                    
                    logger.info(f"🎯 Procesando PrimeFaces {i+1}/{max_details}: {numero_remate}")
                    
                    if self.navigate_to_detail_primefaces(remate):
                        detail_info = self.extract_detail_primefaces()
                        
                        complete_remate = {
                            'numero_remate': numero_remate,
                            'basic_info': {k: v for k, v in remate.items() 
                                         if k not in ['detail_button', 'row_element', 'panel_element']},
                            'detalle': detail_info,
                            'extraction_success': True
                        }
                        
                        detailed_remates.append(complete_remate)
                        self.stats['remates_with_details'] += 1
                        
                        logger.info(f"✅ Detalle PrimeFaces extraído: {numero_remate}")
                    else:
                        failed_remate = {
                            'numero_remate': numero_remate,
                            'basic_info': {k: v for k, v in remate.items() 
                                         if k not in ['detail_button', 'row_element', 'panel_element']},
                            'detalle': {'error': 'No se pudo acceder al detalle PrimeFaces'},
                            'extraction_success': False
                        }
                        detailed_remates.append(failed_remate)
                        logger.warning(f"⚠️ No se pudo extraer detalle PrimeFaces: {numero_remate}")
                    
                    # Regresar para el siguiente
                    if i < max_details - 1:
                        self.return_to_main_if_needed(self.main_page_url)
                        time.sleep(2)
                    
                except Exception as e:
                    logger.error(f"❌ Error procesando remate PrimeFaces {i}: {e}")
                    self.stats['errors'] += 1
                    continue
            
            result = {
                'status': 'success',
                'timestamp': datetime.now().isoformat(),
                'sistema': 'REMAJU_PRIMEFACES',
                'fuente': MAIN_URL,
                'estadisticas': self.generate_stats(),
                'total_remates_encontrados': len(remates),
                'remates_procesados': len(detailed_remates),
                'technology_detected': 'JSF + PrimeFaces',
                'remates': detailed_remates
            }
            
            logger.info(f"🎉 Extracción PrimeFaces completada: {len(detailed_remates)} procesados")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error en extracción PrimeFaces: {e}")
            return self.create_error_result(str(e))
        
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("🔒 Driver PrimeFaces cerrado")
    
    def generate_stats(self):
        """Generar estadísticas de extracción PrimeFaces"""
        duration = (datetime.now() - self.stats['start_time']).total_seconds()
        return {
            'duracion_segundos': round(duration, 2),
            'total_remates_encontrados': self.stats['total_remates'],
            'remates_con_detalle_exitoso': self.stats['remates_with_details'],
            'errores': self.stats['errors'],
            'ajax_calls_detectadas': self.stats['ajax_calls_detected'],
            'tasa_exito_detalle': round(
                (self.stats['remates_with_details'] / max(1, self.stats['total_remates'])) * 100, 2
            ),
            'technology': 'JSF + PrimeFaces',
            'fecha_extraccion': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def create_error_result(self, error_message):
        """Crear resultado de error PrimeFaces"""
        return {
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'error_message': error_message,
            'technology_detected': 'JSF + PrimeFaces',
            'estadisticas': self.generate_stats(),
            'remates': []
        }

def main():
    """Función principal optimizada para PrimeFaces"""
    try:
        logger.info("🚀 Iniciando REMAJU Scraper PrimeFaces")
        
        scraper = REMAJUPrimeFacesScraper()
        resultado = scraper.run_extraction()
        
        # Guardar resultado
        output_file = '/home/claude/remates_primefaces_result.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        # Log resultado
        if resultado['status'] == 'success':
            stats = resultado['estadisticas']
            logger.info(f"🎉 ÉXITO PRIMEFACES")
            logger.info(f"📊 {stats['total_remates_encontrados']} remates encontrados")
            logger.info(f"✅ {stats['remates_con_detalle_exitoso']} con detalle extraído")
            logger.info(f"🔄 {stats['ajax_calls_detectadas']} AJAX calls detectadas")
            logger.info(f"⏱️ Duración: {stats['duracion_segundos']} segundos")
            logger.info(f"📁 Resultado: {output_file}")
            
            print(f"status=success")
            print(f"total_remates={stats['total_remates_encontrados']}")
            print(f"remates_con_detalle={stats['remates_con_detalle_exitoso']}")
            print(f"ajax_calls={stats['ajax_calls_detectadas']}")
            print(f"technology=JSF+PrimeFaces")
        else:
            logger.error(f"❌ ERROR PRIMEFACES: {resultado['error_message']}")
            print(f"status=error")
        
        return resultado
        
    except Exception as e:
        logger.error(f"❌ Error principal PrimeFaces: {e}")
        print(f"status=error")
        return {'status': 'error', 'error_message': str(e)}

if __name__ == "__main__":
    result = main()
    sys.exit(0 if result.get('status') == 'success' else 1)
