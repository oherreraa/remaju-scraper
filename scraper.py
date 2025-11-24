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
from selenium.common.exceptions import TimeoutException

# Configuración global
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://remaju.pj.gob.pe"
MAIN_URL = f"{BASE_URL}/remaju/pages/publico/remateExterno.xhtml"
MAX_DETAILS = int(os.environ.get('MAX_DETAILS', '5'))
HEADLESS = os.environ.get('HEADLESS', 'true').lower() == 'true'

def create_chrome_driver():
    """Configurar driver Chrome optimizado"""
    try:
        chrome_options = Options()
        if HEADLESS:
            chrome_options.add_argument("--headless=new")
        
        # Opciones esenciales
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1366,768")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(60)
        return driver
    except Exception as e:
        logger.error(f"Error configurando driver: {e}")
        return None

def safe_find_element(driver, by, value, timeout=10, optional=False):
    """Buscar elemento de forma segura"""
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
            return ' '.join(text.strip().split())  # Limpiar espacios
        return default
    except:
        return default

def extract_price_info(text):
    """Extraer precio, monto y moneda de texto"""
    if not text:
        return "", 0.0, ""
    
    # Patrones específicos para REMAJU
    patterns = [
        (r'Precio\s+Base\s+(S/\.|\$)\s*([\d,]+\.?\d*)', 1, 2),  # "Precio Base S/. 123,456"
        (r'(S/\.|\$)\s*([\d,]+\.?\d*)', 1, 2),  # "S/. 123,456" o "$ 123,456"
        (r'([\d,]+\.?\d*)\s*(SOLES|DOLARES)', 2, 1),  # "123,456 SOLES"
    ]
    
    for pattern, currency_group, amount_group in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Determinar moneda
            currency_text = match.group(currency_group)
            if currency_text in ["$", "USD", "DOLARES"]:
                currency = "USD"
            else:
                currency = "S/."
            
            # Extraer monto
            amount_str = match.group(amount_group).replace(',', '')
            try:
                amount = float(amount_str)
                return f"{currency} {match.group(amount_group)}", amount, currency
            except:
                return text, 0.0, currency
    
    return text, 0.0, ""

def extract_field_value(lines, labels):
    """Extraer valor de campo por etiquetas"""
    for i, line in enumerate(lines):
        line_lower = line.lower()
        for label in labels:
            if label.lower() in line_lower:
                # Valor en la misma línea después de ':'
                if ':' in line:
                    value = line.split(':', 1)[1].strip()
                    if value and value.lower() != label.lower():
                        return value
                # Valor en línea siguiente
                if i + 1 < len(lines):
                    next_value = lines[i + 1].strip()
                    if next_value and next_value.lower() != label.lower():
                        return next_value
    return ""

class REMAJUScraper:
    """Scraper principal para REMAJU"""
    
    def __init__(self):
        self.driver = None
        self.body_text = ""  # Cache para evitar múltiples llamadas
        self.stats = {
            'start_time': datetime.now(),
            'total_remates': 0,
            'remates_with_details': 0,
            'errors': 0
        }
    
    def setup(self):
        """Configurar scraper"""
        try:
            self.driver = create_chrome_driver()
            if not self.driver:
                return False
            logger.info("Driver configurado correctamente")
            return True
        except Exception as e:
            logger.error(f"Error en setup: {e}")
            return False
    
    def navigate_to_main_page(self):
        """Navegar a página principal"""
        try:
            logger.info("Navegando a REMAJU...")
            self.driver.get(MAIN_URL)
            time.sleep(5)
            
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Cache del texto de la página
            self.body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body"))
            logger.info("Página cargada exitosamente")
            return True
        except Exception as e:
            logger.error(f"Error navegando: {e}")
            return False
    
    def extract_filtros_aplicados(self):
        """Extraer filtros aplicados"""
        filtros = {}
        try:
            if "Publicación e Inscripción" in self.body_text:
                filtros['fase'] = "Publicación e Inscripción"
            
            clear_btn = safe_find_element(self.driver, By.XPATH, 
                "//button[contains(text(), 'Limpiar')] | //a[contains(text(), 'Limpiar')]", 
                optional=True)
            filtros['eliminar_filtros'] = bool(clear_btn)
            
        except Exception as e:
            logger.warning(f"Error extrayendo filtros: {e}")
        
        return filtros
    
    def extract_formulario_filtros(self):
        """Extraer campos del formulario"""
        form_elements = {}
        
        # XPaths simplificados
        field_xpaths = {
            'numero_remate': "//input[contains(@placeholder, 'remate') or contains(@name, 'remate')]",
            'numero_expediente': "//input[contains(@placeholder, 'expediente') or contains(@name, 'expediente')]",
            'precio_base': "//input[contains(@placeholder, 'precio') or contains(@name, 'precio')]",
            'tipo_inmueble': "//select[contains(@name, 'tipo')]",
            'ubicacion': "//select[contains(@name, 'departamento')]",
            'fases': "//select[contains(@name, 'fase')]",
            'captcha': "//img[contains(@src, 'captcha')]",
            'aplicar': "//input[@type='submit']"
        }
        
        for field, xpath in field_xpaths.items():
            element = safe_find_element(self.driver, By.XPATH, xpath, optional=True)
            form_elements[field] = {'available': bool(element)}
        
        return form_elements
    
    def extract_remate_cards_from_page(self):
        """Extraer remates desde cards/tarjetas de REMAJU"""
        remates = []
        try:
            # Esperar carga completa
            time.sleep(5)
            
            # REMAJU usa cards, no tabla tradicional
            # Buscar elementos que contengan "Remate N°"
            card_selectors = [
                "//*[contains(text(), 'Remate N°')]",  # Elementos con "Remate N°"
                "//div[contains(., 'Remate N°')]",     # Divs que contengan "Remate N°"
                "//*[contains(text(), 'PRIMERA CONVOCATORIA')]",  # Por convocatoria
                "//*[contains(text(), 'SEGUNDA CONVOCATORIA')]"
            ]
            
            remate_elements = []
            for selector in card_selectors:
                elements = self.driver.find_elements(By.XPATH, selector)
                remate_elements.extend(elements)
                if elements:
                    logger.info(f"Encontrados {len(elements)} elementos con selector: {selector}")
                    break
            
            if not remate_elements:
                logger.warning("No se encontraron elementos de remate. Extrayendo de texto completo...")
                return self.extract_from_full_text()
            
            # Procesar cada elemento encontrado
            processed_numbers = set()  # Para evitar duplicados
            
            for i, element in enumerate(remate_elements[:20]):  # Máximo 20 para evitar duplicados
                try:
                    # Intentar obtener el contenedor del remate completo
                    # Buscar el div padre que contenga toda la información
                    parent_candidates = [
                        element,
                        element.find_element(By.XPATH, "./.."),           # Padre inmediato
                        element.find_element(By.XPATH, "./../.."),        # Abuelo  
                        element.find_element(By.XPATH, "./../../..")      # Bisabuelo
                    ]
                    
                    best_parent = None
                    max_text_length = 0
                    
                    for candidate in parent_candidates:
                        try:
                            candidate_text = safe_get_text(candidate)
                            if len(candidate_text) > max_text_length and "Precio Base" in candidate_text:
                                best_parent = candidate
                                max_text_length = len(candidate_text)
                        except:
                            continue
                    
                    if not best_parent:
                        best_parent = element
                    
                    card_text = safe_get_text(best_parent)
                    
                    # Extraer número de remate
                    numero_match = re.search(r'Remate\s+N°\s*(\d+)', card_text, re.IGNORECASE)
                    if not numero_match:
                        continue
                    
                    numero_remate = numero_match.group(1)
                    
                    # Evitar duplicados
                    if numero_remate in processed_numbers:
                        continue
                    processed_numbers.add(numero_remate)
                    
                    # Extraer convocatoria
                    if "PRIMERA CONVOCATORIA" in card_text.upper():
                        tipo_convocatoria, numero_convocatoria = "PRIMERA", "PRIMERA CONVOCATORIA"
                    elif "SEGUNDA CONVOCATORIA" in card_text.upper():
                        tipo_convocatoria, numero_convocatoria = "SEGUNDA", "SEGUNDA CONVOCATORIA"
                    else:
                        tipo_convocatoria, numero_convocatoria = "", ""
                    
                    # Extraer tipo de remate
                    tipo_remate = "Judicial"
                    if "REMATE SIMPLE" in card_text:
                        tipo_remate = "Remate Simple"
                    
                    # Extraer ubicación (buscar después del tipo de remate)
                    ubicacion_match = re.search(r'REMATE\s+SIMPLE\s+([A-ZÁÉÍÓÚÑ\s]+)(?:\s+Presentación|$)', card_text, re.IGNORECASE)
                    ubicacion_corta = ubicacion_match.group(1).strip() if ubicacion_match else ""
                    
                    # Extraer fechas y horas
                    fecha_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', card_text)
                    hora_match = re.search(r'(\d{1,2}:\d{2})\s*(?:AM|PM)', card_text)
                    
                    # Extraer estado/fase
                    estado_fase = "Publicación e Inscripción"
                    if "Presentación de Ofertas" in card_text:
                        estado_fase = "Presentación de Ofertas"
                    elif "Validación" in card_text:
                        estado_fase = "Validación"
                    
                    # Extraer precio
                    precio_texto, precio_numerico, moneda = extract_price_info(card_text)
                    
                    # Extraer descripción (buscar texto largo sin fechas ni precios)
                    lines = card_text.split('\n')
                    descripcion = ""
                    for line in lines:
                        line = line.strip()
                        if (len(line) > 50 and 
                            not re.search(r'\d{1,2}/\d{4}|Precio|Remate|Seguimiento|Detalle', line) and
                            line not in ["PRIMERA CONVOCATORIA", "SEGUNDA CONVOCATORIA", "REMATE SIMPLE"]):
                            descripcion = line[:200]
                            break
                    
                    remate_data = {
                        'numero_remate': numero_remate,
                        'tipo_convocatoria': tipo_convocatoria,
                        'numero_convocatoria': numero_convocatoria,
                        'titulo_card': f"Remate N° {numero_remate}" + (f" - {numero_convocatoria}" if numero_convocatoria else ""),
                        'thumbnail_url': "",
                        'no_disponible': False,
                        'tipo_remate': tipo_remate,
                        'ubicacion_corta': ubicacion_corta,
                        'fecha_presentacion_oferta': fecha_match.group(1) if fecha_match else "",
                        'hora_presentacion_oferta': hora_match.group(1) if hora_match else "",
                        'descripcion_corta': descripcion,
                        'estado_fase': estado_fase,
                        'precio_base_texto': precio_texto,
                        'precio_base_numerico': precio_numerico,
                        'moneda': moneda,
                        'acciones': {'seguimiento': "disponible", 'detalle': "disponible", 'aviso': "disponible"},
                        'card_index': len(remates) + 1,
                        'pagina': 1,
                        'posicion_en_pagina': len(remates) + 1
                    }
                    
                    remates.append(remate_data)
                    logger.info(f"Extraído remate {numero_remate}: {ubicacion_corta}")
                    
                except Exception as e:
                    logger.warning(f"Error procesando elemento remate {i}: {e}")
                    continue
            
            self.stats['total_remates'] = len(remates)
            logger.info(f"Extraídos {len(remates)} remates desde cards")
            return remates
            
        except Exception as e:
            logger.error(f"Error extrayendo remates desde cards: {e}")
            return self.extract_from_full_text()
    
    def extract_from_full_text(self):
        """Extraer remates desde texto completo como fallback"""
        remates = []
        try:
            logger.info("Extrayendo remates desde texto completo")
            
            # Actualizar texto completo
            self.body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body"))
            
            # Buscar patrones de "Remate N° XXXXX"
            remate_patterns = re.findall(r'Remate\s+N°\s*(\d+)', self.body_text, re.IGNORECASE)
            
            # Filtrar números únicos que parecen reales (4-6 dígitos)
            unique_remates = []
            for numero in remate_patterns:
                if len(numero) >= 4 and len(numero) <= 6 and numero not in unique_remates:
                    unique_remates.append(numero)
            
            logger.info(f"Encontrados {len(unique_remates)} números de remate únicos")
            
            for i, numero in enumerate(unique_remates[:10]):  # Máximo 10
                # Buscar contexto alrededor de este número
                context_pattern = rf'Remate\s+N°\s*{numero}.*?(?=Remate\s+N°|\Z)'
                context_match = re.search(context_pattern, self.body_text, re.IGNORECASE | re.DOTALL)
                
                context = context_match.group(0) if context_match else f"Remate N° {numero}"
                
                # Extraer información básica del contexto
                precio_texto, precio_numerico, moneda = extract_price_info(context)
                fecha_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', context)
                
                # Convocatoria
                if "PRIMERA" in context.upper():
                    tipo_convocatoria, numero_convocatoria = "PRIMERA", "PRIMERA CONVOCATORIA"
                elif "SEGUNDA" in context.upper():
                    tipo_convocatoria, numero_convocatoria = "SEGUNDA", "SEGUNDA CONVOCATORIA"
                else:
                    tipo_convocatoria, numero_convocatoria = "", ""
                
                remate_data = {
                    'numero_remate': numero,
                    'tipo_convocatoria': tipo_convocatoria,
                    'numero_convocatoria': numero_convocatoria,
                    'titulo_card': f"Remate N° {numero}" + (f" - {numero_convocatoria}" if numero_convocatoria else ""),
                    'thumbnail_url': "",
                    'no_disponible': True,
                    'tipo_remate': "Judicial",
                    'ubicacion_corta': "",
                    'fecha_presentacion_oferta': fecha_match.group(1) if fecha_match else "",
                    'hora_presentacion_oferta': "",
                    'descripcion_corta': f"Remate judicial número {numero}",
                    'estado_fase': "Publicación e Inscripción",
                    'precio_base_texto': precio_texto,
                    'precio_base_numerico': precio_numerico,
                    'moneda': moneda,
                    'acciones': {'seguimiento': "", 'detalle': "disponible", 'aviso': ""},
                    'card_index': i + 1,
                    'pagina': 1,
                    'posicion_en_pagina': i + 1
                }
                
                remates.append(remate_data)
            
            logger.info(f"Extraídos {len(remates)} remates desde texto completo")
            return remates
            
        except Exception as e:
            logger.error(f"Error extrayendo desde texto completo: {e}")
            return []
    
    def navigate_to_detail(self, card_index):
        """Navegar al detalle de un remate - VERSIÓN MEJORADA"""
        try:
            # Buscar botones de detalle con múltiples estrategias
            detail_selectors = [
                "//button[contains(text(), 'Detalle')]",
                "//input[@value='Detalle']", 
                "//a[contains(text(), 'Detalle')]",
                "//button[contains(@onclick, 'detalle')]",
                "//a[contains(@href, 'detalle')]",
                "//a[contains(@href, 'mostrar')]",
                "//*[@title='Detalle']",
                "//button[contains(@class, 'detalle')]",
                "//*[normalize-space(text())='Detalle']",
                "//input[@type='submit' and contains(@value, 'Detalle')]"
            ]
            
            detail_buttons = []
            for selector in detail_selectors:
                try:
                    buttons = self.driver.find_elements(By.XPATH, selector)
                    if buttons:
                        logger.info(f"Encontrados {len(buttons)} botones con selector: {selector}")
                        detail_buttons.extend(buttons)
                        break  # Usar el primer selector que encuentre botones
                except:
                    continue
            
            # Si no encuentra botones específicos, buscar en toda la página
            if not detail_buttons:
                logger.warning("No se encontraron botones con selectores específicos. Buscando en toda la página...")
                
                # Buscar todos los elementos que contengan la palabra "detalle"
                all_elements = self.driver.find_elements(By.XPATH, "//*[contains(translate(text(), 'DETALLE', 'detalle'), 'detalle')]")
                
                for element in all_elements:
                    try:
                        # Verificar si es clickeable
                        if element.is_displayed() and element.is_enabled():
                            tag_name = element.tag_name.lower()
                            if tag_name in ['button', 'a', 'input']:
                                detail_buttons.append(element)
                    except:
                        continue
                
                logger.info(f"Encontrados {len(detail_buttons)} elementos clickeables con 'detalle'")
            
            # Si aún no encuentra, buscar por posición relativa a los remates
            if not detail_buttons:
                logger.warning("Intentando buscar botones por contexto de remate...")
                
                # Buscar elementos que contengan los números de remate que encontramos
                remate_numbers = ["20872", "20871", "20869", "20868"]
                
                for numero in remate_numbers[:card_index + 1]:  # Hasta el índice actual
                    try:
                        # Buscar el elemento que contiene este número de remate
                        remate_element = self.driver.find_element(By.XPATH, f"//*[contains(text(), '{numero}')]")
                        
                        # Buscar botones cerca de este elemento (hermanos, descendientes, etc.)
                        nearby_selectors = [
                            f"//*[contains(text(), '{numero}')]/following-sibling::*//*[contains(text(), 'Detalle')]",
                            f"//*[contains(text(), '{numero}')]/following::*[contains(text(), 'Detalle')][1]",
                            f"//*[contains(text(), '{numero}')]/parent::*//*[contains(text(), 'Detalle')]",
                            f"//*[contains(text(), '{numero}')]/ancestor::*[1]//*[contains(text(), 'Detalle')]"
                        ]
                        
                        for nearby_selector in nearby_selectors:
                            nearby_buttons = self.driver.find_elements(By.XPATH, nearby_selector)
                            if nearby_buttons:
                                detail_buttons.extend(nearby_buttons)
                                logger.info(f"Encontrados botones cerca del remate {numero}")
                                break
                        
                        if detail_buttons:
                            break
                            
                    except Exception as e:
                        continue
            
            if not detail_buttons:
                logger.error("No se pudo encontrar ningún botón de detalle con ningún método")
                
                # Debug: mostrar algunos elementos para entender la estructura
                logger.info("Elementos disponibles para debug:")
                all_buttons = self.driver.find_elements(By.XPATH, "//button | //a | //input[@type='submit']")
                for i, btn in enumerate(all_buttons[:10]):  # Primeros 10
                    try:
                        btn_text = safe_get_text(btn)[:50]  # Primeros 50 caracteres
                        if btn_text:
                            logger.info(f"Botón {i}: {btn_text}")
                    except:
                        continue
                
                return False
            
            # Verificar que el índice sea válido
            if card_index >= len(detail_buttons):
                logger.warning(f"Índice {card_index} fuera de rango. Disponibles: {len(detail_buttons)}")
                # Usar el último botón disponible
                card_index = len(detail_buttons) - 1
            
            button = detail_buttons[card_index]
            
            # Verificar que el botón sea clickeable
            if not (button.is_displayed() and button.is_enabled()):
                logger.warning(f"Botón no clickeable en índice {card_index}")
                return False
            
            # Intentar click
            try:
                logger.info(f"Haciendo click en botón detalle índice {card_index}")
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                time.sleep(1)
                self.driver.execute_script("arguments[0].click();", button)
            except Exception as e:
                logger.warning(f"Error con JavaScript click, intentando click normal: {e}")
                button.click()
            
            # Esperar carga de detalle con múltiples condiciones
            def detail_page_loaded(driver):
                try:
                    body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
                    return any(keyword in body_text for keyword in [
                        "expediente", "tasación", "partida", "distrito judicial", 
                        "precio base", "convocatoria", "tipo de cambio",
                        "cronograma", "inmuebles", "órgano jurisdiccional"
                    ])
                except:
                    return False
            
            try:
                WebDriverWait(self.driver, 15).until(detail_page_loaded)
                
                # Actualizar cache del texto
                self.body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body"))
                logger.info(f"✅ Navegado al detalle (índice {card_index}) exitosamente")
                return True
                
            except TimeoutException:
                logger.warning(f"Timeout esperando carga de página de detalle para índice {card_index}")
                
                # Verificar si al menos cambió la URL
                current_url = self.driver.current_url
                if "detalle" in current_url.lower() or "mostrar" in current_url.lower():
                    logger.info("URL cambió a página de detalle, continuando...")
                    self.body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body"))
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"Error navegando al detalle: {e}")
            return False
    
    def return_to_listing(self):
        """Volver al listado"""
        try:
            back_button = safe_find_element(self.driver, By.XPATH,
                "//button[contains(text(),'Regresar')] | //a[contains(text(),'Regresar')] | //input[@value='Regresar']",
                optional=True)
            
            if back_button and back_button.is_displayed():
                self.driver.execute_script("arguments[0].click();", back_button)
            else:
                self.driver.back()
                
            time.sleep(3)
            
        except Exception as e:
            logger.warning(f"Error volviendo al listado: {e}")
    
    def extract_tab_remate_details(self):
        """Extraer detalles del tab Remate"""
        try:
            lines = [line.strip() for line in self.body_text.split('\n') if line.strip()]
            
            # Bloque expediente
            expediente_fields = {
                'expediente': ["Expediente"],
                'distrito_judicial': ["Distrito Judicial"],
                'organo_jurisdiccional': ["Órgano Jurisdiccional", "Organo Jurisdiccional"],
                'instancia': ["Instancia"],
                'juez': ["Juez"],
                'especialista': ["Especialista"],
                'materia': ["Materia"],
                'resolucion': ["Resolución"],
                'fecha_resolucion': ["Fecha Resolución", "Fecha de Resolución"],
                'archivo_resolucion_url': ""
            }
            
            expediente = {field: extract_field_value(lines, labels) if labels else ""
                         for field, labels in expediente_fields.items()}
            
            # Bloque económico
            economico_fields = {
                'convocatoria': ["Convocatoria"],
                'tipo_cambio': ["Tipo de Cambio", "Tipo Cambio"],
                'tasacion': ["Tasación"],
                'precio_base': ["Precio Base"],
                'incremento_ofertas': ["Incremento entre ofertas", "Incremento"],
                'arancel': ["Arancel"],
                'oblaje': ["Oblaje"],
                'descripcion_completa': ["Descripción"]
            }
            
            economico = {field: extract_field_value(lines, labels)
                        for field, labels in economico_fields.items()}
            
            # Indicadores
            inscritos_text = extract_field_value(lines, ["N° inscritos", "Nº inscritos"])
            inscritos_match = re.search(r'\d+', inscritos_text) if inscritos_text else None
            num_inscritos = int(inscritos_match.group()) if inscritos_match else 0
            
            return {
                'bloque_expediente': expediente,
                'bloque_economico': economico,
                'indicadores': {'num_inscritos': num_inscritos, 'regresar': True}
            }
            
        except Exception as e:
            logger.warning(f"Error en tab Remate: {e}")
            return {}
    
    def extract_tab_inmuebles_details(self):
        """Extraer detalles del tab Inmuebles"""
        try:
            # Intentar activar tab
            tab = safe_find_element(self.driver, By.XPATH,
                "//a[contains(text(), 'Inmuebles')] | //button[contains(text(), 'Inmuebles')]", optional=True)
            if tab and tab.is_displayed():
                self.driver.execute_script("arguments[0].click();", tab)
                time.sleep(2)
                self.body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body"))
            
            inmuebles = []
            
            # Buscar tabla de inmuebles
            table = safe_find_element(self.driver, By.XPATH,
                "//table[.//th[contains(text(), 'Partida')] or .//td[contains(text(), 'TIPO INMUEBLE')]]", optional=True)
            
            if table:
                rows = table.find_elements(By.XPATH, ".//tbody/tr | .//tr[position()>1]")
                
                for i, row in enumerate(rows):
                    try:
                        cells = row.find_elements(By.XPATH, ".//td")
                        if len(cells) >= 4:
                            partida = safe_get_text(cells[0])
                            
                            # Validar que no sea header
                            if partida and not any(word in partida.upper() for word in ['PARTIDA', 'TIPO', 'DIRECCIÓN']):
                                inmueble = {
                                    'partida_registral': partida,
                                    'tipo_inmueble': safe_get_text(cells[1]) if len(cells) > 1 else "",
                                    'direccion': safe_get_text(cells[2]) if len(cells) > 2 else "",
                                    'cargas_gravamenes': safe_get_text(cells[3]) if len(cells) > 3 else "",
                                    'porcentaje_a_rematar': 100.0,
                                    'imagenes_refs': {'count': 0, 'urls': []},
                                    'orden': i + 1
                                }
                                
                                # Extraer porcentaje si existe
                                if len(cells) > 4:
                                    porcentaje_text = safe_get_text(cells[4])
                                    porcentaje_match = re.search(r'(\d+(?:\.\d+)?)%?', porcentaje_text)
                                    if porcentaje_match:
                                        inmueble['porcentaje_a_rematar'] = float(porcentaje_match.group(1))
                                
                                inmuebles.append(inmueble)
                                
                    except Exception as e:
                        logger.warning(f"Error procesando inmueble {i}: {e}")
                        continue
            else:
                # Fallback: extraer de texto
                lines = [line.strip() for line in self.body_text.split('\n') if line.strip()]
                inmueble = {
                    'partida_registral': extract_field_value(lines, ["Partida", "Partida Registral"]),
                    'tipo_inmueble': extract_field_value(lines, ["Tipo", "Tipo Inmueble"]),
                    'direccion': extract_field_value(lines, ["Dirección", "Direccion", "Ubicación"]),
                    'cargas_gravamenes': extract_field_value(lines, ["Cargas", "Gravamen"]),
                    'porcentaje_a_rematar': 100.0,
                    'imagenes_refs': {'count': 0, 'urls': []},
                    'orden': 1
                }
                
                if inmueble['partida_registral'] or inmueble['direccion']:
                    inmuebles.append(inmueble)
            
            logger.info(f"Tab Inmuebles: {len(inmuebles)} extraídos")
            return inmuebles
            
        except Exception as e:
            logger.warning(f"Error en tab Inmuebles: {e}")
            return []
    
    def extract_tab_cronograma_details(self):
        """Extraer detalles del tab Cronograma"""
        try:
            # Intentar activar tab
            tab = safe_find_element(self.driver, By.XPATH,
                "//a[contains(text(), 'Cronograma')] | //button[contains(text(), 'Cronograma')]", optional=True)
            if tab and tab.is_displayed():
                self.driver.execute_script("arguments[0].click();", tab)
                time.sleep(2)
                self.body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body"))
            
            eventos = []
            
            # Patrones de eventos con sus nombres
            event_patterns = [
                (r'inscripci[óo]n.*?(\d{1,2}/\d{1,2}/\d{4}).*?(\d{1,2}:\d{2})', 'Inscripción'),
                (r'exhibici[óo]n.*?(\d{1,2}/\d{1,2}/\d{4}).*?(\d{1,2}:\d{2})', 'Exhibición'),
                (r'presentaci[óo]n.*?ofertas.*?(\d{1,2}/\d{1,2}/\d{4}).*?(\d{1,2}:\d{2})', 'Presentación de ofertas'),
                (r'acto.*?remate.*?(\d{1,2}/\d{1,2}/\d{4}).*?(\d{1,2}:\d{2})', 'Acto de remate')
            ]
            
            for i, (pattern, nombre) in enumerate(event_patterns):
                match = re.search(pattern, self.body_text, re.IGNORECASE | re.DOTALL)
                if match:
                    eventos.append({
                        'evento': nombre,
                        'fecha': match.group(1),
                        'hora': match.group(2),
                        'observacion': "",
                        'orden': i + 1,
                        'regresar': True
                    })
            
            # Fallback: fechas genéricas si no se encontraron eventos específicos
            if not eventos:
                fechas = re.findall(r'(\d{1,2}/\d{1,2}/\d{4})', self.body_text)
                horas = re.findall(r'(\d{1,2}:\d{2})', self.body_text)
                
                for i, fecha in enumerate(fechas[:4]):
                    eventos.append({
                        'evento': f"Evento {i+1}",
                        'fecha': fecha,
                        'hora': horas[i] if i < len(horas) else "",
                        'observacion': "",
                        'orden': i + 1,
                        'regresar': True
                    })
            
            logger.info(f"Tab Cronograma: {len(eventos)} extraídos")
            return eventos
            
        except Exception as e:
            logger.warning(f"Error en tab Cronograma: {e}")
            return []
    
    def extract_complete_details(self):
        """Extraer detalles completos de todos los tabs"""
        return {
            'tab_remate': self.extract_tab_remate_details(),
            'tab_inmuebles': self.extract_tab_inmuebles_details(),
            'tab_cronograma': self.extract_tab_cronograma_details()
        }
    
    def run_extraction(self):
        """Ejecutar extracción completa"""
        try:
            logger.info("Iniciando extracción REMAJU")
            
            if not self.setup() or not self.navigate_to_main_page():
                return self.create_error_result("Error en configuración inicial")
            
            # Extraer módulo principal - USAR CARDS EN LUGAR DE TABLA
            modulo_remates = {
                'filtros_aplicados': self.extract_filtros_aplicados(),
                'formulario_filtros': self.extract_formulario_filtros(),
                'resultados': self.extract_remate_cards_from_page()  # ← CAMBIO PRINCIPAL
            }
            
            # Extraer detalles
            detailed_remates = []
            resultados = modulo_remates['resultados']
            max_details = min(MAX_DETAILS, len(resultados))
            
            for i in range(max_details):
                try:
                    remate = resultados[i]
                    logger.info(f"Procesando {i+1}/{max_details}: {remate.get('numero_remate')}")
                    
                    if self.navigate_to_detail(i):
                        complete_remate = {
                            'numero_remate': remate.get('numero_remate'),
                            'basic_info': remate,
                            'detalle': self.extract_complete_details(),
                            'extraction_timestamp': datetime.now().isoformat(),
                            'source_url': self.driver.current_url
                        }
                        detailed_remates.append(complete_remate)
                        self.stats['remates_with_details'] += 1
                    
                    self.return_to_listing()
                    
                except Exception as e:
                    logger.warning(f"Error procesando detalle {i}: {e}")
                    self.stats['errors'] += 1
            
            return {
                'status': 'success',
                'timestamp': datetime.now().isoformat(),
                'sistema': 'REMAJU',
                'fuente': MAIN_URL,
                'estadisticas': self.generate_stats(),
                'modulo_remates': modulo_remates,
                'modulo_detalle_remates': detailed_remates
            }
            
        except Exception as e:
            logger.error(f"Error en extracción: {e}")
            return self.create_error_result(str(e))
        finally:
            if self.driver:
                self.driver.quit()
    
    def generate_stats(self):
        """Generar estadísticas"""
        duration = (datetime.now() - self.stats['start_time']).total_seconds()
        return {
            'duracion_segundos': round(duration, 2),
            'total_remates_listado': self.stats['total_remates'],
            'remates_con_detalle': self.stats['remates_with_details'],
            'errores': self.stats['errors'],
            'tasa_exito_detalle': round((self.stats['remates_with_details'] / max(1, self.stats['total_remates'])) * 100, 2)
        }
    
    def create_error_result(self, error_message):
        """Crear resultado de error"""
        return {
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'error_message': error_message,
            'estadisticas': self.generate_stats(),
            'modulo_remates': {'resultados': []},
            'modulo_detalle_remates': []
        }

def main():
    """Función principal"""
    try:
        scraper = REMAJUScraper()
        resultado = scraper.run_extraction()
        
        with open('remates_result.json', 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        if resultado['status'] == 'success':
            stats = resultado['estadisticas']
            logger.info(f"ÉXITO - {stats['total_remates_listado']} remates, {stats['remates_con_detalle']} con detalle")
            print(f"total_remates={stats['total_remates_listado']}")
            print(f"remates_con_detalle={stats['remates_con_detalle']}")
            print("status=success")
        else:
            logger.error(f"ERROR: {resultado['error_message']}")
            print("status=error")
        
        return resultado
        
    except Exception as e:
        logger.error(f"Error principal: {e}")
        print("status=error")
        return {'status': 'error', 'error_message': str(e)}

if __name__ == "__main__":
    result = main()
    sys.exit(0 if result.get('status') == 'success' else 1)
