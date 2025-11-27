#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sys
import time
import logging
import re
from datetime import datetime
from typing import Dict, List, Any, Optional

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

# Configuración escalable
MAX_PAGES = int(os.environ.get('MAX_PAGES', '20'))  # Mínimo 20 páginas
MAX_REMATES_TOTAL = int(os.environ.get('MAX_REMATES_TOTAL', '100'))  # Mínimo 80 remates
MAX_DETAILS = int(os.environ.get('MAX_DETAILS', '80'))  # Detalles a extraer
HEADLESS = os.environ.get('HEADLESS', 'true').lower() == 'true'

# ARCHIVO ESPECÍFICO QUE ESPERA EL CI/CD
RESULT_FILE = 'remates_result.json'

# SCHEMA CONSISTENTE - Todos los remates tendrán estos campos
REMATE_SCHEMA = {
    "numero_remate": "",
    "titulo_card": "",
    "ubicacion_corta": "",
    "fecha_presentacion_oferta": "",
    "precio_base_texto": "",
    "precio_base_numerico": 0.0,
    "moneda": "",
    "tipo_convocatoria": "",
    "estado": "",
    "extraction_method": "",
    "page_number": 0,
    "position_in_page": 0
}

DETALLE_SCHEMA = {
    "expediente": "",
    "numero_expediente_completo": "",
    "distrito_judicial": "",
    "organo_jurisdiccional": "",
    "instancia": "",
    "juez": "",
    "especialista": "",
    "materia": "",
    "resolucion_numero": "",
    "fecha_resolucion": "",
    "convocatoria": "",
    "tasacion": "",
    "precio_base": "",
    "incremento_ofertas": "",
    "arancel": "",
    "oblaje": "",
    "descripcion": "",
    "area_m2": "",
    "partida_registral": "",
    "num_inscritos": "",
    "extraction_timestamp": "",
    "source_url": "",
    "extraction_quality": "",
    "quality_score": 0
}

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
    """Configurar driver Chrome para scraping escalable"""
    try:
        chrome_options = Options()
        
        # Configuración para CI/CD
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")  # Acelerar carga
        chrome_options.add_argument("--disable-javascript-harmony-shipping")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Optimizaciones para velocidad
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-features=TranslateUI")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        
        # User agent
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Linux; x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Configuración JavaScript
        chrome_options.add_argument("--enable-javascript")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(60)  # Reducido para velocidad
        driver.implicitly_wait(8)
        
        # Anti-detección
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        logger.info("✅ Driver configurado para scraping escalable")
        return driver
        
    except Exception as e:
        logger.error(f"❌ Error configurando driver: {e}")
        return None

def wait_for_primefaces_ready(driver, timeout=25):
    """Esperar que PrimeFaces esté listo (optimizado)"""
    try:
        logger.debug("⏳ Esperando PrimeFaces...")
        
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return typeof window.PrimeFaces !== 'undefined'")
        )
        
        WebDriverWait(driver, timeout).until(
            lambda d: PrimeFacesWaitConditions.all_ajax_complete(d)
        )
        
        time.sleep(2)  # Reducido
        logger.debug("✅ PrimeFaces listo")
        return True
        
    except:
        logger.warning("⚠️ Timeout PrimeFaces, continuando...")
        return False

def safe_get_text(element, default=""):
    """Obtener texto de forma segura y optimizada"""
    try:
        if element:
            text = element.get_attribute('textContent') or element.text or default
            return ' '.join(text.strip().split())
        return default
    except:
        return default

def apply_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    """Aplicar schema consistente a los datos"""
    result = schema.copy()
    
    for key in schema:
        if key in data and data[key] is not None:
            if isinstance(schema[key], str):
                result[key] = str(data[key])[:500]  # Limitar longitud
            elif isinstance(schema[key], (int, float)):
                try:
                    result[key] = float(data[key]) if data[key] else 0.0
                except:
                    result[key] = 0.0
            else:
                result[key] = data[key]
    
    return result

def extract_price_info(text):
    """Extraer precio y moneda mejorado"""
    if not text:
        return "", 0.0, ""
    
    clean_text = re.sub(r'\s+', ' ', text.strip())
    
    patterns = [
        (r'Precio\s+Base[:\s]*([USD|S/\.|\$]*)\s*([\d,]+\.?\d*)', 1, 2),
        (r'(S/\.|\$|USD)\s*([\d,]+\.?\d*)', 1, 2),
        (r'([\d,]+\.?\d*)\s*(SOLES|DOLARES|USD|S/\.)', 1, 2),
        (r'Base[:\s]*([USD|S/\.|\$]*)\s*([\d,]+\.?\d*)', 1, 2)
    ]
    
    for pattern, currency_group, amount_group in patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            try:
                currency_text = match.group(currency_group)
                amount_text = match.group(amount_group)
                
                currency = "USD" if currency_text in ["$", "USD", "DOLARES"] or "USD" in currency_text.upper() else "S/."
                amount = float(amount_text.replace(',', ''))
                
                return f"{currency} {amount_text}", amount, currency
            except:
                continue
    
    return text, 0.0, ""

class REMAJUScraperScalable:
    """Scraper escalable para múltiples páginas con estructura consistente"""
    
    def __init__(self):
        self.driver = None
        self.main_page_url = ""
        self.current_page = 1
        self.total_remates_extracted = 0
        self.all_remates = []
        self.pagination_info = {
            'current_page': 1,
            'total_pages': 0,
            'pages_processed': 0,
            'has_next_page': True
        }
        self.stats = {
            'start_time': datetime.now(),
            'pages_processed': 0,
            'total_remates_found': 0,
            'total_remates_detailed': 0,
            'pagination_errors': 0,
            'extraction_errors': 0,
            'consistency_errors': 0,
            'field_completion_rates': {}
        }
    
    def setup(self):
        """Configurar scraper escalable"""
        try:
            self.driver = create_chrome_driver()
            if not self.driver:
                return False
            logger.info("✅ Driver configurado para scraping escalable")
            return True
        except Exception as e:
            logger.error(f"❌ Error en setup escalable: {e}")
            return False
    
    def navigate_to_main_page(self):
        """Navegar a página principal"""
        try:
            logger.info("🌐 Navegando a REMAJU para scraping escalable...")
            self.driver.get(MAIN_URL)
            
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            wait_for_primefaces_ready(self.driver, timeout=30)
            
            self.main_page_url = self.driver.current_url
            logger.info(f"✅ Página principal cargada: {self.main_page_url}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error navegando a página principal: {e}")
            return False
    
    def detect_pagination_info(self):
        """Detectar información de paginación"""
        try:
            logger.info("🔍 Detectando información de paginación...")
            
            # Buscar componentes de paginación PrimeFaces
            pagination_selectors = [
                "//div[contains(@class, 'ui-paginator')]",
                "//span[contains(@class, 'ui-paginator')]",
                "//table[contains(@class, 'ui-paginator')]",
                "//div[contains(@class, 'paginator')]"
            ]
            
            pagination_element = None
            for selector in pagination_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements:
                        pagination_element = elements[0]
                        logger.info(f"📄 Paginador encontrado: {selector}")
                        break
                except:
                    continue
            
            if pagination_element:
                pagination_text = safe_get_text(pagination_element)
                logger.info(f"📄 Texto paginador: {pagination_text[:100]}...")
                
                # Buscar total de páginas
                page_match = re.search(r'(\d+)\s*de\s*(\d+)', pagination_text)
                if page_match:
                    current = int(page_match.group(1))
                    total = int(page_match.group(2))
                    self.pagination_info.update({
                        'current_page': current,
                        'total_pages': total,
                        'has_next_page': current < total
                    })
                    logger.info(f"📄 Paginación detectada: {current}/{total} páginas")
                    return True
            
            # Fallback: buscar botones siguiente/anterior
            next_buttons = self.driver.find_elements(By.XPATH, 
                "//button[contains(@class, 'ui-paginator-next')] | "
                "//a[contains(@class, 'ui-paginator-next')] | "
                "//span[contains(@class, 'ui-paginator-next')] | "
                "//button[contains(text(), 'Siguiente')] | "
                "//a[contains(text(), 'Siguiente')]"
            )
            
            if next_buttons:
                self.pagination_info['has_next_page'] = any(btn.is_enabled() for btn in next_buttons)
                logger.info(f"📄 Botón siguiente encontrado: {self.pagination_info['has_next_page']}")
                return True
            
            logger.warning("⚠️ No se detectó paginación, asumiendo página única")
            self.pagination_info.update({
                'total_pages': 1,
                'has_next_page': False
            })
            return True
            
        except Exception as e:
            logger.error(f"❌ Error detectando paginación: {e}")
            return False
    
    def extract_remates_from_current_page(self):
        """Extraer remates de la página actual con schema consistente"""
        try:
            logger.info(f"📋 Extrayendo remates de página {self.current_page}...")
            
            page_remates = []
            
            # Esperar que la página cargue completamente
            time.sleep(3)
            
            # Estrategia 1: Extracción estructurada
            page_remates = self.extract_structured_from_page()
            
            # Estrategia 2: Fallback si no encuentra estructura
            if not page_remates:
                page_remates = self.extract_fallback_from_page()
            
            # Aplicar schema consistente a todos los remates
            consistent_remates = []
            for i, remate_data in enumerate(page_remates):
                remate_data['page_number'] = self.current_page
                remate_data['position_in_page'] = i + 1
                
                consistent_remate = apply_schema(remate_data, REMATE_SCHEMA)
                consistent_remates.append(consistent_remate)
            
            self.stats['total_remates_found'] += len(consistent_remates)
            logger.info(f"✅ Extraídos {len(consistent_remates)} remates de página {self.current_page}")
            
            return consistent_remates
            
        except Exception as e:
            logger.error(f"❌ Error extrayendo remates de página {self.current_page}: {e}")
            self.stats['extraction_errors'] += 1
            return []
    
    def extract_structured_from_page(self):
        """Extracción estructurada de la página"""
        remates = []
        try:
            # Buscar tablas y componentes estructurados
            structured_selectors = [
                "//table[contains(@class, 'ui-datatable')]//tbody//tr",
                "//div[contains(@class, 'ui-datatable')]//tbody//tr",
                "//div[contains(@class, 'ui-datagrid')]//div",
                "//table//tbody//tr[td[contains(text(), 'Remate') or contains(text(), '20')]]",
                "//div[contains(@class, 'remate') or contains(@class, 'item')]"
            ]
            
            for selector in structured_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements:
                        logger.info(f"🎯 Elementos estructurados encontrados: {len(elements)} con {selector}")
                        
                        for i, element in enumerate(elements[:50]):  # Máximo 50 por página
                            try:
                                element_text = safe_get_text(element)
                                
                                if len(element_text) > 30 and self.contains_remate_info(element_text):
                                    remate_data = self.extract_remate_from_element(element, element_text, i)
                                    if remate_data:
                                        remates.append(remate_data)
                                        
                            except Exception as e:
                                continue
                        
                        if remates:
                            break  # Si encontró remates estructurados, usar esos
                            
                except Exception as e:
                    continue
            
            return remates
            
        except Exception as e:
            logger.warning(f"⚠️ Error en extracción estructurada: {e}")
            return []
    
    def extract_fallback_from_page(self):
        """Extracción fallback desde texto de página"""
        remates = []
        try:
            logger.info("🔄 Usando extracción fallback...")
            
            body = self.driver.find_element(By.TAG_NAME, "body")
            body_text = safe_get_text(body)
            
            # Buscar números de remate
            remate_patterns = [
                r'Remate\s+N°?\s*(\d+)',
                r'N°?\s*(\d{4,6})(?:\s|$|[^\d])',
                r'(\d{4,6})\s*[-:]?\s*Remate'
            ]
            
            found_numbers = set()
            for pattern in remate_patterns:
                matches = re.findall(pattern, body_text, re.IGNORECASE)
                found_numbers.update(matches)
            
            unique_numbers = sorted(list(found_numbers))[:30]  # Máximo 30 por página
            logger.info(f"🔍 Números únicos encontrados: {len(unique_numbers)}")
            
            for i, numero in enumerate(unique_numbers):
                try:
                    context = self.extract_context_for_number(body_text, numero)
                    remate_data = self.parse_remate_from_context(numero, context, i)
                    if remate_data:
                        remates.append(remate_data)
                except Exception as e:
                    continue
            
            return remates
            
        except Exception as e:
            logger.error(f"❌ Error en extracción fallback: {e}")
            return []
    
    def contains_remate_info(self, text):
        """Verificar si el texto contiene información de remate"""
        indicators = [
            'remate', 'n°', 'precio', 'base', 'soles', 'dolares', 
            'lima', 'cusco', 'arequipa', 'tasación', '20'
        ]
        text_lower = text.lower()
        return sum(1 for indicator in indicators if indicator in text_lower) >= 2
    
    def extract_remate_from_element(self, element, element_text, position):
        """Extraer información de remate desde elemento"""
        try:
            # Buscar número de remate
            numero_match = re.search(r'Remate\s+N°?\s*(\d+)', element_text, re.IGNORECASE)
            if not numero_match:
                numero_match = re.search(r'(?:^|\s)(\d{4,6})(?:\s|$)', element_text)
            
            if not numero_match:
                return None
            
            numero_remate = numero_match.group(1)
            
            # Extraer información desde celdas si es tabla
            precio_texto, precio_numerico, moneda = "", 0.0, ""
            fecha = ""
            ubicacion = ""
            
            try:
                cells = element.find_elements(By.XPATH, ".//td | .//div | .//span")
                cell_texts = [safe_get_text(cell) for cell in cells if safe_get_text(cell)]
                
                combined_text = " ".join(cell_texts)
                precio_texto, precio_numerico, moneda = extract_price_info(combined_text)
                
                # Fecha
                fecha_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', combined_text)
                fecha = fecha_match.group(1) if fecha_match else ""
                
                # Ubicación
                ciudades = ['LIMA', 'CALLAO', 'AREQUIPA', 'CUSCO', 'TRUJILLO', 'PIURA', 'CHICLAYO', 'HUANCAYO']
                for ciudad in ciudades:
                    if ciudad in combined_text.upper():
                        ubicacion = ciudad
                        break
                        
            except:
                # Fallback a texto del elemento
                precio_texto, precio_numerico, moneda = extract_price_info(element_text)
                fecha_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', element_text)
                fecha = fecha_match.group(1) if fecha_match else ""
                
                ciudades = ['LIMA', 'CALLAO', 'AREQUIPA', 'CUSCO', 'TRUJILLO', 'PIURA']
                for ciudad in ciudades:
                    if ciudad in element_text.upper():
                        ubicacion = ciudad
                        break
            
            # Tipo de convocatoria
            tipo_convocatoria = ""
            if 'primera' in element_text.lower():
                tipo_convocatoria = "PRIMERA CONVOCATORIA"
            elif 'segunda' in element_text.lower():
                tipo_convocatoria = "SEGUNDA CONVOCATORIA"
            
            return {
                'numero_remate': numero_remate,
                'titulo_card': f"Remate N° {numero_remate}",
                'ubicacion_corta': ubicacion,
                'fecha_presentacion_oferta': fecha,
                'precio_base_texto': precio_texto,
                'precio_base_numerico': precio_numerico,
                'moneda': moneda,
                'tipo_convocatoria': tipo_convocatoria,
                'estado': 'ACTIVO',
                'extraction_method': 'structured_element',
                'position_in_page': position
            }
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo de elemento: {e}")
            return None
    
    def extract_context_for_number(self, body_text, numero):
        """Extraer contexto mejorado para un número"""
        try:
            # Estrategia 1: Patrón específico
            pattern = rf'Remate\s+N°?\s*{numero}.*?(?=Remate\s+N°?|\n\n|\Z)'
            match = re.search(pattern, body_text, re.IGNORECASE | re.DOTALL)
            if match and len(match.group(0)) > 50:
                return match.group(0)
            
            # Estrategia 2: Líneas alrededor
            lines = body_text.split('\n')
            for i, line in enumerate(lines):
                if numero in line:
                    start = max(0, i - 5)
                    end = min(len(lines), i + 6)
                    return ' '.join(lines[start:end])
            
            return ""
            
        except:
            return ""
    
    def parse_remate_from_context(self, numero, context, position):
        """Parsear información de remate desde contexto"""
        try:
            precio_texto, precio_numerico, moneda = extract_price_info(context)
            
            fecha_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', context)
            fecha = fecha_match.group(1) if fecha_match else ""
            
            ciudades = ['LIMA', 'CALLAO', 'AREQUIPA', 'CUSCO', 'TRUJILLO', 'PIURA', 'CHICLAYO', 'HUANCAYO']
            ubicacion = ""
            for ciudad in ciudades:
                if ciudad in context.upper():
                    ubicacion = ciudad
                    break
            
            tipo_convocatoria = ""
            if 'primera' in context.lower():
                tipo_convocatoria = "PRIMERA CONVOCATORIA"
            elif 'segunda' in context.lower():
                tipo_convocatoria = "SEGUNDA CONVOCATORIA"
            
            return {
                'numero_remate': numero,
                'titulo_card': f"Remate N° {numero}",
                'ubicacion_corta': ubicacion,
                'fecha_presentacion_oferta': fecha,
                'precio_base_texto': precio_texto,
                'precio_base_numerico': precio_numerico,
                'moneda': moneda,
                'tipo_convocatoria': tipo_convocatoria,
                'estado': 'ACTIVO',
                'extraction_method': 'context_fallback',
                'position_in_page': position
            }
            
        except Exception as e:
            return None
    
    def navigate_to_next_page(self):
        """Navegar a la siguiente página"""
        try:
            logger.info(f"➡️ Navegando de página {self.current_page} a {self.current_page + 1}...")
            
            # Buscar botones de siguiente página
            next_selectors = [
                "//button[contains(@class, 'ui-paginator-next') and not(contains(@class, 'ui-state-disabled'))]",
                "//a[contains(@class, 'ui-paginator-next') and not(contains(@class, 'ui-state-disabled'))]",
                "//span[contains(@class, 'ui-paginator-next') and not(contains(@class, 'ui-state-disabled'))]",
                "//button[contains(text(), 'Siguiente') and not(@disabled)]",
                "//a[contains(text(), 'Siguiente')]",
                f"//a[contains(@class, 'ui-paginator-page') and text()='{self.current_page + 1}']",
                f"//button[contains(@class, 'ui-paginator-page') and text()='{self.current_page + 1}']"
            ]
            
            next_button = None
            for selector in next_selectors:
                try:
                    buttons = self.driver.find_elements(By.XPATH, selector)
                    for button in buttons:
                        if button.is_displayed() and button.is_enabled():
                            next_button = button
                            logger.info(f"📄 Botón siguiente encontrado: {selector}")
                            break
                    if next_button:
                        break
                except:
                    continue
            
            if not next_button:
                logger.warning("⚠️ No se encontró botón de siguiente página")
                self.pagination_info['has_next_page'] = False
                return False
            
            # Hacer click en siguiente
            initial_url = self.driver.current_url
            
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                time.sleep(1)
                self.driver.execute_script("arguments[0].click();", next_button)
                
                # Esperar cambio de página
                if self.wait_for_page_change(initial_url):
                    self.current_page += 1
                    self.pagination_info['current_page'] = self.current_page
                    self.stats['pages_processed'] += 1
                    
                    logger.info(f"✅ Navegación exitosa a página {self.current_page}")
                    return True
                else:
                    logger.warning("⚠️ No se detectó cambio de página")
                    self.pagination_info['has_next_page'] = False
                    return False
                    
            except Exception as e:
                logger.error(f"❌ Error haciendo click en siguiente: {e}")
                self.stats['pagination_errors'] += 1
                return False
            
        except Exception as e:
            logger.error(f"❌ Error navegando a siguiente página: {e}")
            self.stats['pagination_errors'] += 1
            return False
    
    def wait_for_page_change(self, initial_url, timeout=15):
        """Esperar cambio de página"""
        try:
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                current_url = self.driver.current_url
                
                # URL cambió
                if current_url != initial_url:
                    time.sleep(2)
                    wait_for_primefaces_ready(self.driver, timeout=15)
                    return True
                
                # Contenido cambió (para paginación AJAX)
                try:
                    page_indicator = self.driver.find_element(By.XPATH, 
                        "//span[contains(@class, 'ui-paginator-current')] | "
                        "//div[contains(@class, 'ui-paginator')] | "
                        "//span[contains(text(), 'página')]"
                    )
                    indicator_text = safe_get_text(page_indicator)
                    if str(self.current_page + 1) in indicator_text:
                        time.sleep(2)
                        wait_for_primefaces_ready(self.driver, timeout=10)
                        return True
                except:
                    pass
                
                time.sleep(0.5)
            
            return False
            
        except:
            return False
    
    def extract_details_batch(self, remates_list):
        """Extraer detalles de remates en lotes"""
        try:
            detailed_remates = []
            max_details = min(MAX_DETAILS, len(remates_list))
            
            logger.info(f"📊 Procesando detalles para {max_details} remates...")
            
            for i, remate in enumerate(remates_list[:max_details]):
                try:
                    numero_remate = remate.get('numero_remate')
                    logger.info(f"🎯 Detalle {i+1}/{max_details}: {numero_remate} (Página {remate.get('page_number', '?')})")
                    
                    if self.navigate_to_detail_consistent(remate):
                        detail_info = self.extract_detail_consistent()
                        
                        complete_remate = {
                            'numero_remate': numero_remate,
                            'basic_info': remate,
                            'detalle': detail_info,
                            'extraction_success': True
                        }
                        
                        detailed_remates.append(complete_remate)
                        self.stats['total_remates_detailed'] += 1
                        
                        logger.info(f"✅ Detalle extraído: {numero_remate}")
                    else:
                        failed_remate = {
                            'numero_remate': numero_remate,
                            'basic_info': remate,
                            'detalle': apply_schema({}, DETALLE_SCHEMA),
                            'extraction_success': False
                        }
                        detailed_remates.append(failed_remate)
                        logger.warning(f"⚠️ Sin detalle: {numero_remate}")
                    
                    # Regresar a página principal cada 5 remates para evitar timeout
                    if (i + 1) % 5 == 0 or i == max_details - 1:
                        try:
                            logger.info("🔙 Regresando a página principal...")
                            self.driver.get(self.main_page_url)
                            wait_for_primefaces_ready(self.driver, timeout=20)
                            time.sleep(2)
                        except:
                            pass
                    
                except Exception as e:
                    logger.error(f"❌ Error procesando detalle {i}: {e}")
                    continue
            
            return detailed_remates
            
        except Exception as e:
            logger.error(f"❌ Error en extracción de detalles batch: {e}")
            return []
    
    def navigate_to_detail_consistent(self, remate_data):
        """Navegación consistente al detalle"""
        try:
            numero_remate = remate_data.get('numero_remate')
            logger.debug(f"🔍 Navegando al detalle: {numero_remate}")
            
            initial_url = self.driver.current_url
            
            # Re-buscar botones
            button_selectors = [
                "//button[contains(@class, 'ui-button')]",
                "//span[contains(@class, 'ui-button')]",
                "//a[contains(@class, 'ui-button')]",
                "//input[@type='submit']",
                "//button[contains(text(), 'Detalle') or contains(text(), 'Ver')]"
            ]
            
            for selector in button_selectors:
                try:
                    buttons = self.driver.find_elements(By.XPATH, selector)
                    detail_buttons = []
                    
                    for button in buttons:
                        try:
                            if button.is_displayed() and button.is_enabled():
                                btn_text = safe_get_text(button).lower()
                                if any(keyword in btn_text for keyword in ['detalle', 'detail', 'ver', 'consultar', 'info']):
                                    detail_buttons.append(button)
                        except:
                            continue
                    
                    if detail_buttons:
                        logger.debug(f"🎯 Encontrados {len(detail_buttons)} botones de detalle")
                        
                        # Probar botones
                        position = remate_data.get('position_in_page', 0)
                        indices_to_try = [position, 0, 1, 2, 3]
                        
                        for idx in indices_to_try:
                            if idx < len(detail_buttons):
                                try:
                                    button = detail_buttons[idx]
                                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                    time.sleep(0.5)
                                    self.driver.execute_script("arguments[0].click();", button)
                                    
                                    if self.wait_for_detail_load(initial_url):
                                        return True
                                    
                                except:
                                    continue
                        
                        break  # Si encontró botones pero ninguno funcionó
                        
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.debug(f"❌ Error navegando al detalle: {e}")
            return False
    
    def wait_for_detail_load(self, initial_url, timeout=10):
        """Esperar carga de detalle"""
        try:
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                current_url = self.driver.current_url
                
                if current_url != initial_url:
                    time.sleep(1)
                    wait_for_primefaces_ready(self.driver, timeout=8)
                    return True
                
                # Verificar contenido de detalle
                try:
                    body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body")).lower()
                    if any(indicator in body_text for indicator in ['expediente', 'tasación', 'distrito judicial']):
                        return True
                except:
                    pass
                
                time.sleep(0.3)
            
            return False
            
        except:
            return False
    
    def extract_detail_consistent(self):
        """Extraer detalle con schema consistente"""
        try:
            logger.debug("📋 Extrayendo detalle consistente...")
            
            wait_for_primefaces_ready(self.driver, timeout=8)
            
            body_text = ""
            try:
                body = self.driver.find_element(By.TAG_NAME, "body")
                body_text = safe_get_text(body)
            except:
                return apply_schema({'error': 'No se pudo obtener texto'}, DETALLE_SCHEMA)
            
            # Extraer campos usando patrones mejorados
            detail_data = self.extract_fields_comprehensive(body_text)
            
            # Agregar metadatos
            detail_data.update({
                'extraction_timestamp': datetime.now().isoformat(),
                'source_url': self.driver.current_url,
                'extraction_quality': self.assess_detail_quality(detail_data),
                'quality_score': self.calculate_quality_score(detail_data)
            })
            
            # Aplicar schema consistente
            consistent_detail = apply_schema(detail_data, DETALLE_SCHEMA)
            
            return consistent_detail
            
        except Exception as e:
            logger.debug(f"❌ Error extrayendo detalle consistente: {e}")
            return apply_schema({'error': str(e)}, DETALLE_SCHEMA)
    
    def extract_fields_comprehensive(self, body_text):
        """Extracción comprehensiva de campos"""
        detail_data = {}
        
        # Limpiar texto
        clean_text = re.sub(r'\s+', ' ', body_text)
        clean_text = re.sub(r'[^\w\s\-.:/()\u00C0-\u017F]', ' ', clean_text)
        
        # Patrones mejorados para cada campo
        field_patterns = {
            'expediente': [
                r'Expediente[:\s]*([A-Z0-9\-]{10,30})',
                r'N°?\s*Expediente[:\s]*([A-Z0-9\-]{10,30})',
                r'(\d{4,5}\-\d{4}\-\d\-\d{4}\-[A-Z]{2}\-[A-Z]{2}\-\d{2})'
            ],
            'numero_expediente_completo': [
                r'(Exp\w*[:\s]*[A-Z0-9\-]{15,35})',
                r'(Expediente[:\s]*[A-Z0-9\-]{15,35})'
            ],
            'distrito_judicial': [
                r'Distrito\s+Judicial[:\s]*([A-ZÁÉÍÓÚÑ\s]{3,25})(?=\s*(?:Órgano|Instancia|Juez|\n|$))',
            ],
            'organo_jurisdiccional': [
                r'Órgano\s+Jurisdiccional[:\s]*([^:\n]{5,80})(?=\s*(?:Instancia|Juez|\n|$))',
                r'Órgano\s+Jurisdisccional[:\s]*([^:\n]{5,80})(?=\s*(?:Instancia|Juez|\n|$))',
            ],
            'instancia': [
                r'Instancia[:\s]*([A-ZÁÉÍÓÚÑ\s]{5,40})(?=\s*(?:Juez|Especialista|\n|$))',
            ],
            'juez': [
                r'Juez[:\s]*([A-ZÁÉÍÓÚÑ\s]{5,60})(?=\s*(?:Especialista|Materia|\n|$))',
            ],
            'especialista': [
                r'Especialista[:\s]*([A-ZÁÉÍÓÚÑ\s]{5,60})(?=\s*(?:Materia|Resolución|\n|$))',
            ],
            'materia': [
                r'Materia[:\s]*([A-ZÁÉÍÓÚÑ\s]{5,50})(?=\s*(?:Resolución|Fecha|\n|$))',
            ],
            'resolucion_numero': [
                r'Resolución[:\s]*(\d+)',
                r'Resolución\s+N°?\s*(\d+)',
            ],
            'fecha_resolucion': [
                r'Fecha\s+Resolución[:\s]*(\d{1,2}/\d{1,2}/\d{4})',
            ],
            'convocatoria': [
                r'Convocatoria[:\s]*([A-ZÁÉÍÓÚÑ\s]{5,30})(?=\s*(?:Tasación|Precio|\n|$))',
            ],
            'tasacion': [
                r'Tasación[:\s]*([S/\.\$USD\d\s,]+\.?\d*)',
            ],
            'precio_base': [
                r'Precio\s+Base[:\s]*([S/\.\$USD\d\s,]+\.?\d*)',
            ],
            'incremento_ofertas': [
                r'Incremento\s+(?:entre\s+)?ofertas[:\s]*([S/\.\$USD\d\s,]+\.?\d*)',
            ],
            'arancel': [
                r'Arancel[:\s]*([S/\.\$USD\d\s,]+\.?\d*)',
            ],
            'oblaje': [
                r'Oblaje[:\s]*([S/\.\$USD\d\s,]+\.?\d*)',
            ],
            'area_m2': [
                r'(?:AREA|Área)[^0-9]*(\d+\.?\d*)\s*M2',
                r'(\d+\.?\d*)\s*M2',
            ],
            'partida_registral': [
                r'Partida\s+Registral[:\s]*([A-Z0-9]+)',
                r'P(\d{8,12})',
            ],
            'num_inscritos': [
                r'N°?\s*inscritos[:\s]*(\d+)',
                r'inscritos[:\s]*(\d+)',
            ]
        }
        
        # Extraer usando patrones
        for field, patterns in field_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, clean_text, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    value = re.sub(r'^[\s:]+', '', value)
                    value = re.sub(r'\s+', ' ', value)
                    
                    if 2 < len(value) < 200:
                        detail_data[field] = value
                        break
        
        # Descripción (campo más largo)
        desc_patterns = [
            r'Descripción[:\s]*([^:\n]{20,500}?)(?=\s*(?:N°\s*inscritos|Imágenes|\n\n|$))',
            r'(?:DEPARTAMENTO|LOTE|INMUEBLE)[^:\n]*([^:\n]{20,300}?)(?=\s*(?:N°\s*inscritos|\n\n|$))',
        ]
        
        for pattern in desc_patterns:
            match = re.search(pattern, clean_text, re.IGNORECASE | re.DOTALL)
            if match:
                desc = match.group(1).strip()
                desc = re.sub(r'\s+', ' ', desc)
                if len(desc) > 20:
                    detail_data['descripcion'] = desc[:400]  # Limitar longitud
                    break
        
        return detail_data
    
    def assess_detail_quality(self, detail_data):
        """Evaluar calidad de extracción de detalle"""
        important_fields = [
            'expediente', 'distrito_judicial', 'organo_jurisdiccional', 
            'juez', 'precio_base', 'tasacion'
        ]
        
        filled_important = sum(1 for field in important_fields if detail_data.get(field))
        total_filled = sum(1 for v in detail_data.values() if v and str(v).strip())
        
        if filled_important >= 5:
            return 'excelente'
        elif filled_important >= 4:
            return 'alta'
        elif filled_important >= 2:
            return 'media'
        elif total_filled >= 3:
            return 'baja'
        else:
            return 'muy_baja'
    
    def calculate_quality_score(self, detail_data):
        """Calcular score numérico de calidad"""
        field_weights = {
            'expediente': 20,
            'distrito_judicial': 15,
            'organo_jurisdiccional': 15,
            'juez': 15,
            'precio_base': 10,
            'tasacion': 10,
            'convocatoria': 5,
            'descripcion': 5,
            'area_m2': 3,
            'partida_registral': 2
        }
        
        score = 0
        max_score = sum(field_weights.values())
        
        for field, weight in field_weights.items():
            if detail_data.get(field):
                score += weight
        
        return round((score / max_score) * 100, 1)
    
    def update_field_completion_stats(self):
        """Actualizar estadísticas de completitud de campos"""
        if not hasattr(self, 'all_detailed_remates'):
            return
        
        total_remates = len(self.all_detailed_remates)
        if total_remates == 0:
            return
        
        field_counts = {}
        
        # Contar campos completados
        for remate in self.all_detailed_remates:
            detalle = remate.get('detalle', {})
            for field in DETALLE_SCHEMA.keys():
                if field not in field_counts:
                    field_counts[field] = 0
                if detalle.get(field) and str(detalle[field]).strip():
                    field_counts[field] += 1
        
        # Calcular porcentajes
        for field, count in field_counts.items():
            self.stats['field_completion_rates'][field] = round((count / total_remates) * 100, 2)
    
    def save_result(self, result):
        """Guardar resultado en remates_result.json"""
        try:
            with open(RESULT_FILE, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            logger.info(f"💾 Resultado escalable guardado en: {RESULT_FILE}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error guardando resultado: {e}")
            return False
    
    def run_scalable_extraction(self):
        """Ejecutar extracción escalable de múltiples páginas"""
        try:
            logger.info(f"🚀 Iniciando REMAJU Scraper Escalable - Target: {MAX_PAGES} páginas, {MAX_REMATES_TOTAL} remates")
            
            if not self.setup():
                return self.create_error_result("Error en configuración escalable")
            
            if not self.navigate_to_main_page():
                return self.create_error_result("Error navegando a página principal")
            
            # Detectar información de paginación
            self.detect_pagination_info()
            
            # Procesar páginas
            while (self.current_page <= MAX_PAGES and 
                   self.total_remates_extracted < MAX_REMATES_TOTAL and
                   self.pagination_info['has_next_page']):
                
                try:
                    logger.info(f"📄 Procesando página {self.current_page}/{MAX_PAGES}")
                    
                    # Extraer remates de la página actual
                    page_remates = self.extract_remates_from_current_page()
                    
                    if page_remates:
                        self.all_remates.extend(page_remates)
                        self.total_remates_extracted += len(page_remates)
                        
                        logger.info(f"✅ Página {self.current_page}: {len(page_remates)} remates "
                                  f"(Total acumulado: {self.total_remates_extracted})")
                    else:
                        logger.warning(f"⚠️ Página {self.current_page}: 0 remates encontrados")
                    
                    # Verificar si alcanzó el límite
                    if self.total_remates_extracted >= MAX_REMATES_TOTAL:
                        logger.info(f"🎯 Límite de remates alcanzado: {self.total_remates_extracted}")
                        break
                    
                    # Navegar a siguiente página
                    if self.current_page < MAX_PAGES:
                        if not self.navigate_to_next_page():
                            logger.info("📄 No hay más páginas disponibles")
                            break
                    else:
                        logger.info(f"📄 Límite de páginas alcanzado: {MAX_PAGES}")
                        break
                    
                    # Pausa entre páginas para evitar sobrecarga
                    time.sleep(1)
                    
                except Exception as e:
                    logger.error(f"❌ Error procesando página {self.current_page}: {e}")
                    self.stats['extraction_errors'] += 1
                    break
            
            logger.info(f"📊 Extracción de páginas completada: {self.total_remates_extracted} remates de {self.current_page} páginas")
            
            # Extraer detalles de remates seleccionados
            if self.all_remates:
                self.all_detailed_remates = self.extract_details_batch(self.all_remates)
                self.update_field_completion_stats()
            else:
                return self.create_error_result("No se encontraron remates en ninguna página")
            
            # Crear resultado final
            result = {
                'status': 'success',
                'timestamp': datetime.now().isoformat(),
                'sistema': 'REMAJU_ESCALABLE',
                'fuente': MAIN_URL,
                'configuracion': {
                    'max_pages_target': MAX_PAGES,
                    'max_remates_target': MAX_REMATES_TOTAL,
                    'max_details_target': MAX_DETAILS
                },
                'estadisticas': self.generate_scalable_stats(),
                'pagination_info': self.pagination_info,
                'consistency_metrics': self.generate_consistency_metrics(),
                'total_remates_encontrados': self.total_remates_extracted,
                'total_remates_detallados': len(self.all_detailed_remates),
                'technology_detected': 'JSF + PrimeFaces (Escalable)',
                'remates': self.all_detailed_remates
            }
            
            # Guardar resultado
            if self.save_result(result):
                logger.info(f"🎉 Extracción escalable completada: {len(self.all_detailed_remates)} remates detallados")
                return result
            else:
                return self.create_error_result("Error guardando resultado escalable")
            
        except Exception as e:
            logger.error(f"❌ Error en ejecución escalable: {e}")
            return self.create_error_result(str(e))
        
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("🔒 Driver escalable cerrado")
    
    def generate_scalable_stats(self):
        """Generar estadísticas escalables"""
        duration = (datetime.now() - self.stats['start_time']).total_seconds()
        return {
            'duracion_segundos': round(duration, 2),
            'paginas_procesadas': self.stats['pages_processed'],
            'total_remates_encontrados': self.stats['total_remates_found'],
            'total_remates_detallados': self.stats['total_remates_detailed'],
            'errores_paginacion': self.stats['pagination_errors'],
            'errores_extraccion': self.stats['extraction_errors'],
            'errores_consistencia': self.stats['consistency_errors'],
            'promedio_remates_por_pagina': round(
                self.stats['total_remates_found'] / max(1, self.stats['pages_processed']), 2
            ),
            'tasa_exito_detalle': round(
                (self.stats['total_remates_detailed'] / max(1, self.stats['total_remates_found'])) * 100, 2
            ),
            'field_completion_rates': self.stats['field_completion_rates'],
            'fecha_extraccion': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def generate_consistency_metrics(self):
        """Generar métricas de consistencia"""
        if not hasattr(self, 'all_detailed_remates'):
            return {}
        
        total_remates = len(self.all_detailed_remates)
        if total_remates == 0:
            return {}
        
        # Verificar consistencia de campos básicos
        basic_fields = ['numero_remate', 'titulo_card', 'ubicacion_corta', 'precio_base_texto']
        basic_consistency = sum(
            1 for remate in self.all_detailed_remates 
            if all(remate.get('basic_info', {}).get(field) for field in basic_fields)
        )
        
        # Verificar consistencia de campos de detalle
        detail_fields = ['expediente', 'distrito_judicial', 'organo_jurisdiccional']
        detail_consistency = sum(
            1 for remate in self.all_detailed_remates 
            if all(remate.get('detalle', {}).get(field) for field in detail_fields)
        )
        
        # Calcular scores de calidad
        quality_scores = [
            remate.get('detalle', {}).get('quality_score', 0) 
            for remate in self.all_detailed_remates
        ]
        avg_quality_score = round(sum(quality_scores) / len(quality_scores), 2) if quality_scores else 0
        
        return {
            'basic_info_consistency': round((basic_consistency / total_remates) * 100, 2),
            'detail_info_consistency': round((detail_consistency / total_remates) * 100, 2),
            'average_quality_score': avg_quality_score,
            'quality_distribution': {
                'excelente': sum(1 for r in self.all_detailed_remates if r.get('detalle', {}).get('extraction_quality') == 'excelente'),
                'alta': sum(1 for r in self.all_detailed_remates if r.get('detalle', {}).get('extraction_quality') == 'alta'),
                'media': sum(1 for r in self.all_detailed_remates if r.get('detalle', {}).get('extraction_quality') == 'media'),
                'baja': sum(1 for r in self.all_detailed_remates if r.get('detalle', {}).get('extraction_quality') == 'baja')
            }
        }
    
    def create_error_result(self, error_message):
        """Crear resultado de error escalable"""
        result = {
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'error_message': error_message,
            'estadisticas': self.generate_scalable_stats(),
            'pagination_info': self.pagination_info,
            'remates': []
        }
        
        try:
            self.save_result(result)
        except:
            pass
        
        return result

def main():
    """Función principal escalable"""
    try:
        logger.info(f"🚀 REMAJU Scraper Escalable - Target: {MAX_PAGES} páginas, {MAX_REMATES_TOTAL} remates")
        
        scraper = REMAJUScraperScalable()
        resultado = scraper.run_scalable_extraction()
        
        if resultado['status'] == 'success':
            stats = resultado['estadisticas']
            consistency = resultado.get('consistency_metrics', {})
            pagination = resultado.get('pagination_info', {})
            
            logger.info(f"🎉 ÉXITO ESCALABLE")
            logger.info(f"📄 Páginas procesadas: {stats['paginas_procesadas']}")
            logger.info(f"📊 {stats['total_remates_encontrados']} remates encontrados")
            logger.info(f"✅ {stats['total_remates_detallados']} remates detallados")
            logger.info(f"📈 Promedio por página: {stats['promedio_remates_por_pagina']}")
            logger.info(f"🎯 Consistencia básica: {consistency.get('basic_info_consistency', 0)}%")
            logger.info(f"🎯 Calidad promedio: {consistency.get('average_quality_score', 0)}")
            logger.info(f"⏱️ Duración: {stats['duracion_segundos']} segundos")
            
            print(f"SUCCESS: {stats['total_remates_encontrados']} remates de {stats['paginas_procesadas']} páginas")
            return 0
        else:
            logger.error(f"❌ ERROR ESCALABLE: {resultado['error_message']}")
            print(f"ERROR: {resultado['error_message']}")
            return 1
        
    except Exception as e:
        logger.error(f"❌ Error crítico escalable: {e}")
        
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
