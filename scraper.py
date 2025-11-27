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
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
from selenium.webdriver.common.action_chains import ActionChains

# Configuración global
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://remaju.pj.gob.pe"
MAIN_URL = f"{BASE_URL}/remaju/pages/publico/remateExterno.xhtml"
MAX_DETAILS = int(os.environ.get('MAX_DETAILS', '3'))
HEADLESS = os.environ.get('HEADLESS', 'false').lower() == 'true'

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
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Opciones adicionales para estabilidad
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")  # Cargar más rápido
        chrome_options.add_argument("--disable-javascript-harmony-shipping")
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(90)
        driver.implicitly_wait(5)
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

def wait_for_page_change(driver, initial_url, timeout=15):
    """Esperar que cambie la URL de la página"""
    try:
        WebDriverWait(driver, timeout).until(lambda d: d.current_url != initial_url)
        return True
    except TimeoutException:
        return False

def extract_price_info(text):
    """Extraer precio, monto y moneda de texto"""
    if not text:
        return "", 0.0, ""
    
    # Patrones específicos para REMAJU
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

class REMAJUScraperImproved:
    """Scraper mejorado para REMAJU"""
    
    def __init__(self):
        self.driver = None
        self.current_url = ""
        self.main_page_url = ""
        self.stats = {
            'start_time': datetime.now(),
            'total_remates': 0,
            'remates_with_details': 0,
            'errors': 0,
            'navigation_errors': 0
        }
    
    def setup(self):
        """Configurar scraper"""
        try:
            self.driver = create_chrome_driver()
            if not self.driver:
                return False
            logger.info("✅ Driver configurado correctamente")
            return True
        except Exception as e:
            logger.error(f"❌ Error en setup: {e}")
            return False
    
    def navigate_to_main_page(self):
        """Navegar a página principal"""
        try:
            logger.info("🌐 Navegando a REMAJU...")
            self.driver.get(MAIN_URL)
            
            # Esperar carga completa
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Espera adicional para JavaScript
            time.sleep(8)
            
            self.main_page_url = self.driver.current_url
            logger.info(f"✅ Página principal cargada: {self.main_page_url}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error navegando a página principal: {e}")
            return False
    
    def extract_remates_from_page(self):
        """Extraer remates de la página principal - MÉTODO MEJORADO"""
        remates = []
        try:
            logger.info("📋 Extrayendo remates de la página...")
            
            # Esperar carga completa
            time.sleep(5)
            
            # Estrategia 1: Buscar por patrones de texto "Remate N°"
            body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body"))
            remate_numbers = re.findall(r'Remate\s+N°?\s*(\d+)', body_text, re.IGNORECASE)
            
            # Filtrar y obtener números únicos
            unique_numbers = []
            for num in remate_numbers:
                if len(num) >= 4 and len(num) <= 6 and num not in unique_numbers:
                    unique_numbers.append(num)
            
            logger.info(f"🔍 Encontrados {len(unique_numbers)} números de remate únicos")
            
            # Estrategia 2: Buscar elementos que contengan información de remates
            remate_elements = []
            
            # Buscar divs o elementos que contengan números de remate
            for numero in unique_numbers[:10]:  # Límite para pruebas
                try:
                    # Buscar elementos que contengan este número específico
                    elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{numero}')]")
                    
                    for element in elements:
                        try:
                            # Buscar el contenedor más grande que tenga información relevante
                            parent = element
                            for _ in range(5):  # Buscar hasta 5 niveles arriba
                                try:
                                    parent_candidate = parent.find_element(By.XPATH, "./..")
                                    parent_text = safe_get_text(parent_candidate)
                                    
                                    # Si el padre tiene información de precio y es sustancial, usarlo
                                    if (len(parent_text) > len(safe_get_text(parent)) and 
                                        any(keyword in parent_text.lower() for keyword in ['precio', 'base', 'convocatoria', 'remate'])):
                                        parent = parent_candidate
                                    else:
                                        break
                                except:
                                    break
                            
                            element_text = safe_get_text(parent)
                            if len(element_text) > 100:  # Solo elementos con contenido sustancial
                                remate_elements.append({
                                    'numero': numero,
                                    'element': parent,
                                    'text': element_text
                                })
                                break  # Solo uno por número de remate
                        except:
                            continue
                except:
                    continue
            
            logger.info(f"🎯 Encontrados {len(remate_elements)} elementos de remate con contenido")
            
            # Procesar elementos encontrados
            for i, remate_info in enumerate(remate_elements):
                try:
                    numero_remate = remate_info['numero']
                    text = remate_info['text']
                    element = remate_info['element']
                    
                    # Extraer información básica
                    precio_texto, precio_numerico, moneda = extract_price_info(text)
                    
                    # Extraer convocatoria
                    if "PRIMERA CONVOCATORIA" in text.upper():
                        tipo_convocatoria = "PRIMERA"
                        numero_convocatoria = "PRIMERA CONVOCATORIA"
                    elif "SEGUNDA CONVOCATORIA" in text.upper():
                        tipo_convocatoria = "SEGUNDA"
                        numero_convocatoria = "SEGUNDA CONVOCATORIA"
                    else:
                        tipo_convocatoria = ""
                        numero_convocatoria = ""
                    
                    # Extraer fecha
                    fecha_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', text)
                    hora_match = re.search(r'(\d{1,2}:\d{2})', text)
                    
                    # Extraer ubicación/descripción
                    ubicacion = ""
                    descripcion = ""
                    
                    # Buscar palabras clave de ubicación
                    ubicacion_patterns = [
                        r'(?:LIMA|CALLAO|PIURA|TRUJILLO|AREQUIPA|CUSCO|HUANCAYO|CHICLAYO|TACNA|ICA)[^,\n]*',
                        r'(?:DISTRITO|PROVINCIA|DEPARTAMENTO)\s+[A-ZÁÉÍÓÚÑ\s]+',
                    ]
                    
                    for pattern in ubicacion_patterns:
                        match = re.search(pattern, text, re.IGNORECASE)
                        if match:
                            ubicacion = match.group().strip()[:50]
                            break
                    
                    # Buscar línea más descriptiva
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    for line in lines:
                        if (len(line) > 30 and len(line) < 200 and
                            not re.search(r'Remate|Precio|Convocatoria|\d{2}/\d{4}', line)):
                            descripcion = line
                            break
                    
                    # Buscar botón de detalle asociado a este elemento
                    detail_button = None
                    try:
                        # Buscar dentro del elemento o sus hermanos
                        detail_selectors = [
                            ".//button[contains(text(), 'Detalle')]",
                            ".//input[@value='Detalle']",
                            ".//a[contains(text(), 'Detalle')]",
                            ".//following-sibling::*//button[contains(text(), 'Detalle')]",
                            ".//preceding-sibling::*//button[contains(text(), 'Detalle')]"
                        ]
                        
                        for selector in detail_selectors:
                            try:
                                button = element.find_element(By.XPATH, selector)
                                if button.is_displayed() and button.is_enabled():
                                    detail_button = button
                                    break
                            except:
                                continue
                        
                    except:
                        pass
                    
                    remate_data = {
                        'numero_remate': numero_remate,
                        'tipo_convocatoria': tipo_convocatoria,
                        'numero_convocatoria': numero_convocatoria,
                        'titulo_card': f"Remate N° {numero_remate}" + (f" - {numero_convocatoria}" if numero_convocatoria else ""),
                        'ubicacion_corta': ubicacion,
                        'fecha_presentacion_oferta': fecha_match.group(1) if fecha_match else "",
                        'hora_presentacion_oferta': hora_match.group(1) if hora_match else "",
                        'descripcion_corta': descripcion,
                        'precio_base_texto': precio_texto,
                        'precio_base_numerico': precio_numerico,
                        'moneda': moneda,
                        'element_reference': element,  # Guardar referencia para navegación
                        'detail_button': detail_button,  # Botón específico si se encontró
                        'card_index': i,
                        'posicion_en_pagina': i + 1
                    }
                    
                    remates.append(remate_data)
                    logger.info(f"✅ Remate {numero_remate} extraído: {ubicacion}")
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error procesando remate {i}: {e}")
                    continue
            
            self.stats['total_remates'] = len(remates)
            logger.info(f"📊 Total extraído: {len(remates)} remates")
            return remates
            
        except Exception as e:
            logger.error(f"❌ Error extrayendo remates: {e}")
            return []
    
    def navigate_to_detail(self, remate_data):
        """Navegar al detalle de un remate - VERSIÓN COMPLETAMENTE MEJORADA"""
        try:
            numero_remate = remate_data.get('numero_remate')
            logger.info(f"🔍 Navegando al detalle del remate {numero_remate}")
            
            initial_url = self.driver.current_url
            
            # Estrategia 1: Usar botón específico si se encontró
            if remate_data.get('detail_button'):
                try:
                    button = remate_data['detail_button']
                    logger.info("🎯 Usando botón específico encontrado")
                    
                    # Scroll al botón y hacer click
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                    time.sleep(1)
                    
                    # Intentar click JavaScript primero
                    self.driver.execute_script("arguments[0].click();", button)
                    
                    if self.wait_for_navigation_or_modal():
                        logger.info("✅ Navegación exitosa con botón específico")
                        return True
                        
                except Exception as e:
                    logger.warning(f"⚠️ Error con botón específico: {e}")
            
            # Estrategia 2: Buscar botones cerca del elemento del remate
            if remate_data.get('element_reference'):
                try:
                    element = remate_data['element_reference']
                    logger.info("🔍 Buscando botones cerca del elemento del remate")
                    
                    # Buscar botones de detalle en contexto del elemento
                    context_selectors = [
                        ".//button[contains(translate(text(), 'DETALLE', 'detalle'), 'detalle')]",
                        ".//input[contains(translate(@value, 'DETALLE', 'detalle'), 'detalle')]",
                        ".//a[contains(translate(text(), 'DETALLE', 'detalle'), 'detalle')]",
                        ".//*[contains(@onclick, 'detalle') or contains(@onclick, 'mostrar')]",
                        ".//following::button[contains(text(), 'Detalle')][1]",
                        ".//ancestor::*//button[contains(text(), 'Detalle')]"
                    ]
                    
                    for selector in context_selectors:
                        try:
                            buttons = element.find_elements(By.XPATH, selector)
                            for button in buttons:
                                if button.is_displayed() and button.is_enabled():
                                    logger.info(f"🎯 Intentando botón encontrado con: {selector}")
                                    
                                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                    time.sleep(1)
                                    self.driver.execute_script("arguments[0].click();", button)
                                    
                                    if self.wait_for_navigation_or_modal():
                                        logger.info("✅ Navegación exitosa con botón contextual")
                                        return True
                                    
                        except Exception as e:
                            continue
                            
                except Exception as e:
                    logger.warning(f"⚠️ Error buscando botones contextuales: {e}")
            
            # Estrategia 3: Buscar todos los botones de detalle en la página
            try:
                logger.info("🔍 Buscando todos los botones de detalle en la página")
                
                global_selectors = [
                    "//button[contains(translate(text(), 'DETALLE', 'detalle'), 'detalle')]",
                    "//input[contains(translate(@value, 'DETALLE', 'detalle'), 'detalle')]",
                    "//a[contains(translate(text(), 'DETALLE', 'detalle'), 'detalle')]",
                    "//*[contains(@onclick, 'detalle') or contains(@onclick, 'mostrar')]"
                ]
                
                all_detail_buttons = []
                for selector in global_selectors:
                    try:
                        buttons = self.driver.find_elements(By.XPATH, selector)
                        for button in buttons:
                            if button.is_displayed() and button.is_enabled():
                                all_detail_buttons.append(button)
                    except:
                        continue
                
                logger.info(f"🔍 Encontrados {len(all_detail_buttons)} botones de detalle")
                
                # Intentar con el botón correspondiente al índice
                card_index = remate_data.get('card_index', 0)
                if card_index < len(all_detail_buttons):
                    try:
                        button = all_detail_buttons[card_index]
                        logger.info(f"🎯 Intentando botón índice {card_index}")
                        
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                        time.sleep(1)
                        self.driver.execute_script("arguments[0].click();", button)
                        
                        if self.wait_for_navigation_or_modal():
                            logger.info("✅ Navegación exitosa con botón por índice")
                            return True
                            
                    except Exception as e:
                        logger.warning(f"⚠️ Error con botón por índice: {e}")
                
                # Intentar con todos los botones si el índice no funcionó
                for i, button in enumerate(all_detail_buttons[:5]):  # Máximo 5 intentos
                    try:
                        logger.info(f"🎯 Intentando botón global {i}")
                        
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                        time.sleep(1)
                        self.driver.execute_script("arguments[0].click();", button)
                        
                        if self.wait_for_navigation_or_modal():
                            logger.info(f"✅ Navegación exitosa con botón global {i}")
                            return True
                        else:
                            # Si no navegó, volver a la página principal para el siguiente intento
                            if self.driver.current_url != initial_url:
                                self.return_to_main_page()
                            
                    except Exception as e:
                        logger.warning(f"⚠️ Error con botón global {i}: {e}")
                        continue
                        
            except Exception as e:
                logger.warning(f"⚠️ Error en búsqueda global de botones: {e}")
            
            # Estrategia 4: Buscar por texto del remate en links
            try:
                logger.info("🔍 Buscando links que contengan el número de remate")
                
                remate_links = self.driver.find_elements(By.XPATH, f"//a[contains(text(), '{numero_remate}')]")
                
                for link in remate_links:
                    try:
                        if link.is_displayed() and link.is_enabled():
                            logger.info(f"🎯 Intentando link con número de remate")
                            
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
                            time.sleep(1)
                            self.driver.execute_script("arguments[0].click();", link)
                            
                            if self.wait_for_navigation_or_modal():
                                logger.info("✅ Navegación exitosa con link del remate")
                                return True
                                
                    except Exception as e:
                        continue
                        
            except Exception as e:
                logger.warning(f"⚠️ Error buscando links del remate: {e}")
            
            logger.error(f"❌ No se pudo navegar al detalle del remate {numero_remate}")
            self.stats['navigation_errors'] += 1
            return False
            
        except Exception as e:
            logger.error(f"❌ Error navegando al detalle: {e}")
            self.stats['navigation_errors'] += 1
            return False
    
    def wait_for_navigation_or_modal(self, timeout=15):
        """Esperar navegación o modal de detalle"""
        try:
            initial_url = self.driver.current_url
            
            # Esperar hasta que ocurra uno de estos cambios
            def check_navigation():
                current_url = self.driver.current_url
                body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body")).lower()
                
                # Verificar cambio de URL
                if current_url != initial_url:
                    return True
                
                # Verificar contenido de detalle en la misma página (modal o actualización AJAX)
                detail_indicators = [
                    'expediente', 'tasación', 'partida registral', 
                    'órgano jurisdiccional', 'cronograma', 
                    'inmuebles', 'resolución', 'distrito judicial'
                ]
                
                return any(indicator in body_text for indicator in detail_indicators)
            
            # Esperar con timeout
            start_time = time.time()
            while time.time() - start_time < timeout:
                if check_navigation():
                    time.sleep(2)  # Esperar estabilización
                    return True
                time.sleep(0.5)
            
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ Error esperando navegación: {e}")
            return False
    
    def return_to_main_page(self):
        """Volver a la página principal"""
        try:
            logger.info("🔙 Regresando a página principal...")
            
            # Intentar botón regresar primero
            back_selectors = [
                "//button[contains(translate(text(), 'REGRESAR', 'regresar'), 'regresar')]",
                "//a[contains(translate(text(), 'REGRESAR', 'regresar'), 'regresar')]",
                "//input[contains(translate(@value, 'REGRESAR', 'regresar'), 'regresar')]",
                "//button[contains(text(), 'Volver')]",
                "//a[contains(text(), 'Volver')]"
            ]
            
            for selector in back_selectors:
                try:
                    back_button = safe_find_element(self.driver, By.XPATH, selector, timeout=5, optional=True)
                    if back_button and back_button.is_displayed() and back_button.is_enabled():
                        logger.info("🎯 Usando botón regresar")
                        self.driver.execute_script("arguments[0].click();", back_button)
                        time.sleep(3)
                        return True
                except:
                    continue
            
            # Si no hay botón, navegar directamente
            if self.main_page_url and self.driver.current_url != self.main_page_url:
                logger.info("🌐 Navegando directamente a página principal")
                self.driver.get(self.main_page_url)
                time.sleep(5)
                return True
            
            # Último recurso: usar browser back
            logger.info("⬅️ Usando navegación hacia atrás")
            self.driver.back()
            time.sleep(3)
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Error regresando: {e}")
            return False
    
    def extract_detail_info(self):
        """Extraer información detallada de la página actual"""
        try:
            logger.info("📋 Extrayendo información detallada...")
            
            # Esperar carga completa
            time.sleep(3)
            
            body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body"))
            
            # Extraer información básica del detalle
            detail_info = {
                'expediente': self.extract_field_from_text(body_text, ['Expediente', 'N° Expediente']),
                'distrito_judicial': self.extract_field_from_text(body_text, ['Distrito Judicial']),
                'organo_jurisdiccional': self.extract_field_from_text(body_text, ['Órgano Jurisdiccional']),
                'precio_base': self.extract_field_from_text(body_text, ['Precio Base']),
                'tasacion': self.extract_field_from_text(body_text, ['Tasación']),
                'convocatoria': self.extract_field_from_text(body_text, ['Convocatoria']),
                'juez': self.extract_field_from_text(body_text, ['Juez']),
                'materia': self.extract_field_from_text(body_text, ['Materia']),
                'full_text_length': len(body_text),
                'extraction_timestamp': datetime.now().isoformat(),
                'source_url': self.driver.current_url
            }
            
            # Intentar extraer tabs si existen
            detail_info['tabs'] = self.extract_tabs_info()
            
            logger.info(f"✅ Detalle extraído: {detail_info.get('expediente', 'N/A')}")
            return detail_info
            
        except Exception as e:
            logger.error(f"❌ Error extrayendo detalle: {e}")
            return {
                'error': str(e),
                'extraction_timestamp': datetime.now().isoformat(),
                'source_url': self.driver.current_url if self.driver else 'unknown'
            }
    
    def extract_field_from_text(self, text, field_labels):
        """Extraer valor de campo del texto usando múltiples labels"""
        for label in field_labels:
            # Patrón: label seguido de : y valor
            pattern = rf'{re.escape(label)}\s*:?\s*([^\n\r]+)'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                # Limpiar valor común
                value = re.sub(r'^[\s:]+', '', value)
                if len(value) > 3:  # Solo valores sustanciales
                    return value
        return ""
    
    def extract_tabs_info(self):
        """Extraer información de tabs si están disponibles"""
        tabs_info = {}
        
        try:
            # Buscar tabs visibles
            tab_selectors = [
                "//a[contains(@class, 'tab') or contains(@role, 'tab')]",
                "//button[contains(@class, 'tab') or contains(@role, 'tab')]",
                "//li[contains(@class, 'tab')]//a",
                "//*[contains(text(), 'Remate') or contains(text(), 'Inmuebles') or contains(text(), 'Cronograma')]"
            ]
            
            tabs_found = []
            for selector in tab_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        text = safe_get_text(element).strip()
                        if (text and len(text) < 50 and 
                            any(keyword in text.lower() for keyword in ['remate', 'inmuebles', 'cronograma', 'detalles'])):
                            tabs_found.append({
                                'text': text,
                                'element': element
                            })
                except:
                    continue
            
            logger.info(f"🔍 Encontrados {len(tabs_found)} tabs potenciales")
            
            # Intentar hacer click en cada tab y extraer contenido
            for tab in tabs_found[:3]:  # Máximo 3 tabs
                try:
                    tab_name = tab['text'].lower()
                    element = tab['element']
                    
                    if element.is_displayed() and element.is_enabled():
                        logger.info(f"🎯 Explorando tab: {tab['text']}")
                        
                        # Click en el tab
                        self.driver.execute_script("arguments[0].click();", element)
                        time.sleep(2)
                        
                        # Extraer contenido del tab
                        tab_content = safe_get_text(self.driver.find_element(By.TAG_NAME, "body"))
                        
                        # Procesar según el tipo de tab
                        if 'inmuebles' in tab_name:
                            tabs_info['inmuebles'] = self.extract_inmuebles_from_content(tab_content)
                        elif 'cronograma' in tab_name:
                            tabs_info['cronograma'] = self.extract_cronograma_from_content(tab_content)
                        else:
                            tabs_info[tab_name] = {
                                'content_length': len(tab_content),
                                'extracted_at': datetime.now().isoformat()
                            }
                        
                except Exception as e:
                    logger.warning(f"⚠️ Error explorando tab {tab.get('text', 'unknown')}: {e}")
                    continue
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo tabs: {e}")
        
        return tabs_info
    
    def extract_inmuebles_from_content(self, content):
        """Extraer información de inmuebles del contenido"""
        inmuebles = []
        
        try:
            # Buscar partidas registrales
            partidas = re.findall(r'(\d{11,})', content)  # Partidas suelen ser números largos
            
            # Buscar direcciones
            direcciones = re.findall(r'(?:Ubicado|Dirección|Sito)[^.]*\.', content, re.IGNORECASE)
            
            # Buscar tipos de inmueble
            tipos = re.findall(r'(Casa|Departamento|Terreno|Local|Oficina|Lote)[^.]*', content, re.IGNORECASE)
            
            # Combinar información encontrada
            max_items = max(len(partidas), len(direcciones), len(tipos))
            
            for i in range(min(max_items, 5)):  # Máximo 5 inmuebles
                inmueble = {
                    'partida_registral': partidas[i] if i < len(partidas) else "",
                    'direccion': direcciones[i] if i < len(direcciones) else "",
                    'tipo': tipos[i] if i < len(tipos) else "",
                    'orden': i + 1
                }
                inmuebles.append(inmueble)
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo inmuebles: {e}")
        
        return inmuebles
    
    def extract_cronograma_from_content(self, content):
        """Extraer cronograma del contenido"""
        eventos = []
        
        try:
            # Buscar fechas en el contenido
            fechas = re.findall(r'(\d{1,2}/\d{1,2}/\d{4})', content)
            
            # Buscar eventos asociados a fechas
            fases = [
                'Publicación e Inscripción',
                'Validación de Inscripción',
                'Presentación de Ofertas',
                'Pago del Saldo'
            ]
            
            for i, fase in enumerate(fases):
                fecha_asociada = fechas[i] if i < len(fechas) else ""
                
                if fecha_asociada or fase.lower() in content.lower():
                    evento = {
                        'evento': fase,
                        'fecha': fecha_asociada,
                        'orden': i + 1
                    }
                    eventos.append(evento)
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo cronograma: {e}")
        
        return eventos
    
    def run_extraction(self):
        """Ejecutar extracción completa - FLUJO MEJORADO"""
        try:
            logger.info("🚀 Iniciando extracción mejorada de REMAJU")
            
            # Setup inicial
            if not self.setup():
                return self.create_error_result("Error en configuración inicial")
            
            if not self.navigate_to_main_page():
                return self.create_error_result("Error navegando a página principal")
            
            # Extraer listado principal
            remates = self.extract_remates_from_page()
            
            if not remates:
                return self.create_error_result("No se encontraron remates en la página")
            
            # Extraer detalles
            detailed_remates = []
            max_details = min(MAX_DETAILS, len(remates))
            
            logger.info(f"📊 Procesando detalles para {max_details} remates de {len(remates)} encontrados")
            
            for i in range(max_details):
                try:
                    remate = remates[i]
                    numero_remate = remate.get('numero_remate')
                    
                    logger.info(f"🎯 Procesando {i+1}/{max_details}: Remate {numero_remate}")
                    
                    if self.navigate_to_detail(remate):
                        detail_info = self.extract_detail_info()
                        
                        complete_remate = {
                            'numero_remate': numero_remate,
                            'basic_info': {k: v for k, v in remate.items() 
                                         if k not in ['element_reference', 'detail_button']},
                            'detalle': detail_info,
                            'extraction_success': True
                        }
                        
                        detailed_remates.append(complete_remate)
                        self.stats['remates_with_details'] += 1
                        
                        logger.info(f"✅ Detalle extraído para remate {numero_remate}")
                    else:
                        # Agregar información básica aunque no se pueda acceder al detalle
                        failed_remate = {
                            'numero_remate': numero_remate,
                            'basic_info': {k: v for k, v in remate.items() 
                                         if k not in ['element_reference', 'detail_button']},
                            'detalle': {'error': 'No se pudo acceder al detalle'},
                            'extraction_success': False
                        }
                        detailed_remates.append(failed_remate)
                        logger.warning(f"⚠️ No se pudo extraer detalle para remate {numero_remate}")
                    
                    # Regresar a página principal para el siguiente remate
                    if i < max_details - 1:  # No regresar en el último
                        self.return_to_main_page()
                        time.sleep(3)
                    
                except Exception as e:
                    logger.error(f"❌ Error procesando remate {i}: {e}")
                    self.stats['errors'] += 1
                    continue
            
            # Resultado final
            result = {
                'status': 'success',
                'timestamp': datetime.now().isoformat(),
                'sistema': 'REMAJU',
                'fuente': MAIN_URL,
                'estadisticas': self.generate_stats(),
                'total_remates_encontrados': len(remates),
                'remates_procesados': len(detailed_remates),
                'remates': detailed_remates,
                'listado_basico': [
                    {k: v for k, v in remate.items() 
                     if k not in ['element_reference', 'detail_button']}
                    for remate in remates
                ]
            }
            
            logger.info(f"🎉 Extracción completada: {len(detailed_remates)} remates procesados")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error en extracción principal: {e}")
            return self.create_error_result(str(e))
        
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("🔒 Driver cerrado")
    
    def generate_stats(self):
        """Generar estadísticas de la extracción"""
        duration = (datetime.now() - self.stats['start_time']).total_seconds()
        return {
            'duracion_segundos': round(duration, 2),
            'total_remates_encontrados': self.stats['total_remates'],
            'remates_con_detalle_exitoso': self.stats['remates_with_details'],
            'errores_navegacion': self.stats['navigation_errors'],
            'errores_procesamiento': self.stats['errors'],
            'tasa_exito_detalle': round(
                (self.stats['remates_with_details'] / max(1, self.stats['total_remates'])) * 100, 2
            ),
            'fecha_extraccion': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def create_error_result(self, error_message):
        """Crear resultado de error"""
        return {
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'error_message': error_message,
            'estadisticas': self.generate_stats(),
            'remates': []
        }

def main():
    """Función principal"""
    try:
        logger.info("🚀 Iniciando REMAJU Scraper Mejorado")
        
        scraper = REMAJUScraperImproved()
        resultado = scraper.run_extraction()
        
        # Guardar resultado
        output_file = '/home/claude/remates_result_improved.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        # Log resultado
        if resultado['status'] == 'success':
            stats = resultado['estadisticas']
            logger.info(f"🎉 ÉXITO - {stats['total_remates_encontrados']} remates encontrados, "
                       f"{stats['remates_con_detalle_exitoso']} con detalle extraído")
            logger.info(f"📁 Resultado guardado en: {output_file}")
            
            print(f"status=success")
            print(f"total_remates={stats['total_remates_encontrados']}")
            print(f"remates_con_detalle={stats['remates_con_detalle_exitoso']}")
            print(f"duracion={stats['duracion_segundos']}")
        else:
            logger.error(f"❌ ERROR: {resultado['error_message']}")
            print(f"status=error")
        
        return resultado
        
    except Exception as e:
        logger.error(f"❌ Error principal: {e}")
        print(f"status=error")
        return {'status': 'error', 'error_message': str(e)}

if __name__ == "__main__":
    result = main()
    sys.exit(0 if result.get('status') == 'success' else 1)
