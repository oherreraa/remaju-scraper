#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REMAJU Scraper - Versión Corregida y Organizada
Sistema de scraping para remates judiciales con estructura jerárquica modular

Estructura corregida:
1. Módulo "Remates" (Listado Principal)
   - Filtros aplicados
   - Formulario de filtros  
   - Resultados (cards repetibles)

2. Módulo "Detalle" (Por cada remate)
   - Tab "Remate" (datos generales)
   - Tab "Inmuebles" (lista de bienes)
   - Tab "Cronograma" (eventos del remate)

Autor: Oha
Fecha: Noviembre 2025
"""

import json
import os
import sys
import time
import logging
import re
from datetime import datetime
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# ========================================
# CONFIGURACIÓN Y LOGGING
# ========================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('remaju_scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Configuración global
BASE_URL = "https://remaju.pj.gob.pe"
MAIN_URL = f"{BASE_URL}/remaju/pages/publico/remateExterno.xhtml"
MAX_PAGES = int(os.environ.get('MAX_PAGES', '10'))
MAX_DETAILS = int(os.environ.get('MAX_DETAILS', '5'))
HEADLESS = os.environ.get('HEADLESS', 'true').lower() == 'true'

# Expresiones regulares útiles
REMATE_REGEX = re.compile(r"remate\s+n[°º]?\s*(\d+)", re.IGNORECASE)
PRECIO_REGEX = re.compile(r'(S/\.|USD|\$|€)?\s*([\d,\.]+)')

# XPaths comunes
DETALLE_XPATH = "//button[normalize-space(.)='Detalle'] | //a[normalize-space(.)='Detalle'] | //input[@value='Detalle']"

# ========================================
# CONFIGURACIÓN DEL DRIVER
# ========================================

def setup_driver():
    """Configurar driver Chrome optimizado"""
    try:
        chrome_options = Options()
        
        if HEADLESS:
            chrome_options.add_argument("--headless=new")
        
        # Opciones de optimización
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1366,768")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(60)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        logger.info("✅ Driver configurado correctamente")
        return driver
        
    except Exception as e:
        logger.error(f"❌ Error configurando driver: {e}")
        return None

# ========================================
# UTILIDADES COMUNES
# ========================================

def safe_find_element(driver, by, value, timeout=10, optional=False):
    """Buscar elemento de forma segura"""
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
    except TimeoutException:
        if not optional:
            logger.warning(f"⚠️ Elemento no encontrado: {value}")
        return None

def safe_find_elements(driver, by, value, timeout=10):
    """Buscar múltiples elementos de forma segura"""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
        return driver.find_elements(by, value)
    except TimeoutException:
        return []

def get_text_safe(element, default=""):
    """Extraer texto de elemento de forma segura"""
    try:
        if element:
            return element.get_attribute('textContent') or element.text or default
        return default
    except:
        return default

def extract_value_from_lines(lines, labels):
    """Buscar etiquetas en líneas de texto y devolver valor"""
    for i, line in enumerate(lines):
        line_lower = line.lower()
        for label in labels:
            label_lower = label.lower()
            if label_lower in line_lower:
                # Buscar valor en la misma línea
                idx = line_lower.find(label_lower)
                after = line[idx + len(label):].strip(" :\t-")
                if after:
                    return after
                # Si no hay valor, buscar en línea siguiente
                if i + 1 < len(lines):
                    return lines[i + 1].strip()
    return ""

# ========================================
# MÓDULO 1: REMATES (LISTADO)
# ========================================

class ModuloRemates:
    """Clase para manejar el módulo de listado de remates"""
    
    def __init__(self, driver):
        self.driver = driver
        
    def extract_filtros_aplicados(self):
        """Extraer filtros aplicados actualmente"""
        filtros = {}
        
        try:
            # Buscar chips de filtros
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            if "Publicación e Inscripción" in page_text:
                filtros['fase'] = "Publicación e Inscripción"
            
            # Buscar botón eliminar filtros
            clear_btn = safe_find_element(self.driver, By.XPATH, 
                "//a[contains(., 'Limpiar')] | //button[contains(., 'Limpiar')]", 
                optional=True)
            filtros['eliminar_filtros'] = bool(clear_btn)
            
            logger.info(f"📋 Filtros aplicados: {filtros}")
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo filtros: {e}")
            
        return filtros
    
    def extract_formulario_filtros(self):
        """Extraer campos del formulario de filtros"""
        form_elements = {}
        
        try:
            # Mapeo de campos comunes
            fields = {
                'numero_remate': "//input[@placeholder='Número de Remate' or contains(@name, 'remate')]",
                'numero_expediente': "//input[@placeholder='Expediente' or contains(@name, 'expediente')]", 
                'precio_base': "//input[@placeholder='Precio Base' or contains(@name, 'precio')]",
                'tipo_inmueble': "//select[contains(@name, 'tipo') or contains(@name, 'inmueble')]",
                'ubicacion': "//select[contains(@name, 'ubicacion') or contains(@name, 'departamento')]",
                'fases': "//select[contains(@name, 'fase') or contains(@name, 'estado')]"
            }
            
            for field_name, xpath in fields.items():
                element = safe_find_element(self.driver, By.XPATH, xpath, optional=True)
                form_elements[field_name] = {
                    'available': bool(element),
                    'type': element.tag_name if element else None
                }
            
            # CAPTCHA y botón aplicar
            captcha = safe_find_element(self.driver, By.XPATH, "//img[contains(@src, 'captcha')]", optional=True)
            apply_btn = safe_find_element(self.driver, By.XPATH, "//input[@type='submit'] | //button[@type='submit']", optional=True)
            
            form_elements['captcha'] = {'available': bool(captcha)}
            form_elements['aplicar'] = {'available': bool(apply_btn)}
            
            logger.info(f"📝 Formulario de filtros: {len([f for f in form_elements.values() if f.get('available')])} campos disponibles")
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo formulario: {e}")
            
        return form_elements
    
    def extract_remate_card(self, card_text, card_index):
        """Extraer datos de una tarjeta/card individual de remate"""
        card_data = {}
        
        try:
            lines = [l.strip() for l in card_text.split('\n') if l.strip()]
            
            # Número de remate
            match = REMATE_REGEX.search(card_text)
            card_data['numero_remate'] = match.group(1) if match else f"REMATE_{card_index}"
            
            # Número y tipo de convocatoria
            if "PRIMERA" in card_text.upper():
                card_data['tipo_convocatoria'] = "PRIMERA"
                card_data['numero_convocatoria'] = "PRIMERA CONVOCATORIA"
            elif "SEGUNDA" in card_text.upper():
                card_data['tipo_convocatoria'] = "SEGUNDA" 
                card_data['numero_convocatoria'] = "SEGUNDA CONVOCATORIA"
            else:
                card_data['tipo_convocatoria'] = ""
                card_data['numero_convocatoria'] = ""
            
            # Título de la card (primera línea con "REMATE")
            title_line = next((line for line in lines if "REMATE" in line.upper()), "")
            card_data['titulo_card'] = title_line
            
            # Imagen thumbnail (por ahora no disponible)
            card_data['thumbnail_url'] = ""
            card_data['no_disponible'] = True
            
            # Tipo de remate
            card_data['tipo_remate'] = "Judicial"  # Por defecto
            
            # Ubicación corta
            ubicacion = ""
            for line in lines:
                if any(keyword in line.upper() for keyword in ["LIMA", "CALLAO", "AREQUIPA", "CUSCO", "TRUJILLO"]):
                    ubicacion = line.strip()
                    break
            card_data['ubicacion_corta'] = ubicacion
            
            # Fechas (buscar patrones de fecha)
            fecha_pattern = r'\d{1,2}/\d{1,2}/\d{4}'
            hora_pattern = r'\d{1,2}:\d{2}'
            
            fecha_match = re.search(fecha_pattern, card_text)
            hora_match = re.search(hora_pattern, card_text)
            
            card_data['fecha_presentacion_oferta'] = fecha_match.group() if fecha_match else ""
            card_data['hora_presentacion_oferta'] = hora_match.group() if hora_match else ""
            
            # Descripción corta
            desc_lines = [line for line in lines if len(line) > 30 and "REMATE" not in line.upper()]
            card_data['descripcion_corta'] = desc_lines[0] if desc_lines else ""
            
            # Estado/fase
            if "PUBLICACIÓN" in card_text.upper():
                card_data['estado_fase'] = "Publicación e Inscripción"
            else:
                card_data['estado_fase'] = "En proceso"
            
            # Precio base
            precio_match = PRECIO_REGEX.search(card_text)
            if precio_match:
                moneda = precio_match.group(1) or "S/."
                numero_str = precio_match.group(2).replace(',', '').replace('.', '')
                
                card_data['precio_base_texto'] = f"{moneda} {precio_match.group(2)}"
                card_data['moneda'] = moneda
                try:
                    # Convertir a float manejando decimales
                    if '.' in precio_match.group(2):
                        card_data['precio_base_numerico'] = float(precio_match.group(2).replace(',', ''))
                    else:
                        card_data['precio_base_numerico'] = float(numero_str)
                except:
                    card_data['precio_base_numerico'] = 0.0
            else:
                card_data['precio_base_texto'] = ""
                card_data['precio_base_numerico'] = 0.0
                card_data['moneda'] = ""
            
            # Acciones (se llenarán al encontrar botones)
            card_data['acciones'] = {
                'seguimiento': "",
                'detalle': "detalle_disponible",  # Marcador genérico
                'aviso': ""
            }
            
            # Metadatos
            card_data['card_index'] = card_index
            
            return card_data
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo card {card_index}: {e}")
            return {'card_index': card_index, 'numero_remate': f"ERROR_{card_index}"}
    
    def extract_resultados(self):
        """Extraer todos los resultados (cards) del listado"""
        resultados = []
        page_num = 1
        
        try:
            while page_num <= MAX_PAGES:
                logger.info(f"📄 Procesando página {page_num}")
                
                # Esperar a que cargue el contenido
                time.sleep(2)
                
                # Obtener texto de toda la página para análisis
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
                
                # Buscar patrones de remates en el texto
                remate_matches = list(REMATE_REGEX.finditer(page_text))
                
                if not remate_matches:
                    logger.warning(f"⚠️ No se encontraron remates en página {page_num}")
                    break
                
                logger.info(f"📋 Encontrados {len(remate_matches)} remates en página {page_num}")
                
                # Extraer información de cada remate encontrado
                for i, match in enumerate(remate_matches):
                    try:
                        # Obtener contexto alrededor del match
                        start_pos = max(0, match.start() - 200)
                        end_pos = min(len(page_text), match.end() + 500)
                        remate_context = page_text[start_pos:end_pos]
                        
                        card_data = self.extract_remate_card(remate_context, len(resultados) + 1)
                        card_data['pagina'] = page_num
                        card_data['posicion_en_pagina'] = i + 1
                        
                        resultados.append(card_data)
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Error procesando remate {i} en página {page_num}: {e}")
                        continue
                
                # Navegar a siguiente página
                if page_num >= MAX_PAGES:
                    logger.info(f"🔄 Límite de páginas alcanzado: {MAX_PAGES}")
                    break
                    
                if not self.navigate_to_next_page(page_num + 1):
                    logger.info("🏁 No hay más páginas disponibles")
                    break
                    
                page_num += 1
            
            logger.info(f"✅ Total resultados extraídos: {len(resultados)} remates en {page_num} páginas")
            return resultados
            
        except Exception as e:
            logger.error(f"❌ Error extrayendo resultados: {e}")
            return resultados
    
    def navigate_to_next_page(self, target_page):
        """Navegar a la página siguiente"""
        try:
            # Intentar enlaces numéricos
            page_link = safe_find_element(self.driver, By.XPATH, 
                f"//a[normalize-space(text())='{target_page}']", optional=True)
            
            if page_link and page_link.is_displayed():
                self.driver.execute_script("arguments[0].click();", page_link)
                time.sleep(3)
                return True
            
            # Intentar botón "Siguiente"
            next_button = safe_find_element(self.driver, By.XPATH,
                "//a[contains(., 'Siguiente') or contains(., '»') or contains(., '>')]", 
                optional=True)
            
            if next_button and next_button.is_displayed():
                self.driver.execute_script("arguments[0].click();", next_button)
                time.sleep(3)
                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ Error navegando a página {target_page}: {e}")
            return False

# ========================================
# MÓDULO 2: DETALLE (TABS)
# ========================================

class ModuloDetalle:
    """Clase para manejar el módulo de detalles de remates"""
    
    def __init__(self, driver):
        self.driver = driver
    
    def navigate_to_detail(self, card_index):
        """Navegar al detalle de un remate específico"""
        try:
            # Buscar botones de detalle
            detail_buttons = safe_find_elements(self.driver, By.XPATH, DETALLE_XPATH)
            
            if not detail_buttons or card_index >= len(detail_buttons):
                logger.warning(f"⚠️ No se encontró botón detalle para índice {card_index}")
                return False
            
            button = detail_buttons[card_index]
            if not (button.is_displayed() and button.is_enabled()):
                return False
            
            # Click en el botón
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            time.sleep(0.5)
            self.driver.execute_script("arguments[0].click();", button)
            
            # Esperar que cargue la página de detalle
            def detail_loaded(driver):
                text = driver.find_element(By.TAG_NAME, "body").text.lower()
                return "expediente" in text or "tasación" in text
            
            WebDriverWait(self.driver, 10).until(detail_loaded)
            logger.info(f"✅ Navegado al detalle (índice {card_index})")
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Error navegando al detalle: {e}")
            return False
    
    def return_to_listing(self):
        """Volver al listado desde el detalle"""
        try:
            # Buscar botón regresar
            back_button = safe_find_element(self.driver, By.XPATH,
                "//button[contains(.,'Regresar')] | //a[contains(.,'Regresar')]",
                optional=True)
            
            if back_button and back_button.is_displayed():
                self.driver.execute_script("arguments[0].click();", back_button)
                time.sleep(3)
            else:
                # Fallback: usar navegación del browser
                self.driver.back()
                time.sleep(3)
            
            # Esperar que cargue el listado
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, DETALLE_XPATH))
            )
            
        except Exception as e:
            logger.warning(f"⚠️ Error volviendo al listado: {e}")
    
    def extract_tab_remate(self):
        """Extraer datos del Tab 'Remate' (datos generales)"""
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            lines = [l.strip() for l in page_text.split('\n') if l.strip()]
            
            # Bloque expediente/juzgado
            bloque_expediente = {
                'expediente': extract_value_from_lines(lines, ["Expediente"]),
                'distrito_judicial': extract_value_from_lines(lines, ["Distrito Judicial"]),
                'organo_jurisdiccional': extract_value_from_lines(lines, [
                    "Órgano Jurisdiccional", "Organo Jurisdiccional", "Órgano Jurisdisccional"
                ]),
                'instancia': extract_value_from_lines(lines, ["Instancia"]),
                'juez': extract_value_from_lines(lines, ["Juez"]),
                'especialista': extract_value_from_lines(lines, ["Especialista"]),
                'materia': extract_value_from_lines(lines, ["Materia"]),
                'resolucion': extract_value_from_lines(lines, ["Resolución"]),
                'fecha_resolucion': extract_value_from_lines(lines, ["Fecha Resolución", "Fecha de Resolución"]),
                'archivo_resolucion_url': ""  # Se llenaría si hay enlaces
            }
            
            # Bloque económico/convocatoria
            bloque_economico = {
                'convocatoria': extract_value_from_lines(lines, ["Convocatoria"]),
                'tipo_cambio': extract_value_from_lines(lines, ["Tipo Cambio"]),
                'tasacion': extract_value_from_lines(lines, ["Tasación"]),
                'precio_base': extract_value_from_lines(lines, ["Precio Base"]),
                'incremento_ofertas': extract_value_from_lines(lines, ["Incremento entre ofertas"]),
                'arancel': extract_value_from_lines(lines, ["Arancel"]),
                'oblaje': extract_value_from_lines(lines, ["Oblaje"]),
                'descripcion_completa': extract_value_from_lines(lines, ["Descripción"])
            }
            
            # Indicadores
            inscritos_text = extract_value_from_lines(lines, ["N° inscritos", "Nº inscritos"])
            num_inscritos = 0
            if inscritos_text:
                match = re.search(r'\d+', inscritos_text)
                num_inscritos = int(match.group()) if match else 0
            
            indicadores = {
                'num_inscritos': num_inscritos,
                'regresar': True
            }
            
            return {
                'bloque_expediente': bloque_expediente,
                'bloque_economico': bloque_economico,
                'indicadores': indicadores
            }
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo tab Remate: {e}")
            return {}
    
    def extract_tab_inmuebles(self):
        """Extraer datos del Tab 'Inmuebles' (lista de bienes)"""
        try:
            # Intentar hacer clic en tab Inmuebles
            inmuebles_tab = safe_find_element(self.driver, By.XPATH,
                "//a[contains(., 'Inmuebles')] | //button[contains(., 'Inmuebles')]",
                optional=True)
            
            if inmuebles_tab:
                self.driver.execute_script("arguments[0].click();", inmuebles_tab)
                time.sleep(2)
            
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            lines = [l.strip() for l in page_text.split('\n') if l.strip()]
            
            # Buscar tabla de inmuebles
            inmuebles = []
            
            # Datos del primer inmueble (asumiendo uno por remate)
            inmueble_data = {
                'partida_registral': extract_value_from_lines(lines, ["Partida Registral", "Partida"]),
                'tipo_inmueble': extract_value_from_lines(lines, ["Tipo", "Tipo Inmueble"]),
                'direccion': extract_value_from_lines(lines, ["Dirección", "Direccion", "Ubicación"]),
                'cargas_gravamenes': extract_value_from_lines(lines, ["Carga", "Gravamen"]),
                'porcentaje_a_rematar': 100.0,  # Por defecto
                'imagenes_refs': {
                    'count': 0,
                    'urls': []
                },
                'orden': 1
            }
            
            # Buscar porcentaje específico
            porcentaje_text = extract_value_from_lines(lines, ["Porcentaje"])
            if porcentaje_text:
                match = re.search(r'(\d+(?:\.\d+)?)%?', porcentaje_text)
                if match:
                    inmueble_data['porcentaje_a_rematar'] = float(match.group(1))
            
            if inmueble_data['partida_registral'] or inmueble_data['direccion']:
                inmuebles.append(inmueble_data)
            
            logger.info(f"✅ Tab Inmuebles: {len(inmuebles)} inmuebles extraídos")
            return inmuebles
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo tab Inmuebles: {e}")
            return []
    
    def extract_tab_cronograma(self):
        """Extraer datos del Tab 'Cronograma' (eventos del remate)"""
        try:
            # Intentar hacer clic en tab Cronograma
            cronograma_tab = safe_find_element(self.driver, By.XPATH,
                "//a[contains(., 'Cronograma')] | //button[contains(., 'Cronograma')]",
                optional=True)
            
            if cronograma_tab:
                self.driver.execute_script("arguments[0].click();", cronograma_tab)
                time.sleep(2)
            
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            # Buscar eventos típicos en el cronograma
            eventos = []
            
            # Eventos comunes en cronogramas
            eventos_comunes = [
                "Inscripción",
                "Exhibición", 
                "Presentación de ofertas",
                "Acto de remate"
            ]
            
            for i, evento_tipo in enumerate(eventos_comunes):
                if evento_tipo.lower() in page_text.lower():
                    # Buscar fechas cercanas al evento
                    fecha_match = re.search(rf'{evento_tipo}.*?(\d{{1,2}}/\d{{1,2}}/\d{{4}})', page_text, re.IGNORECASE)
                    hora_match = re.search(rf'{evento_tipo}.*?(\d{{1,2}}:\d{{2}})', page_text, re.IGNORECASE)
                    
                    evento_data = {
                        'hito': evento_tipo,
                        'evento': evento_tipo,
                        'fecha': fecha_match.group(1) if fecha_match else "",
                        'hora': hora_match.group(1) if hora_match else "",
                        'observacion': "",
                        'orden': i + 1,
                        'regresar': True
                    }
                    eventos.append(evento_data)
            
            logger.info(f"✅ Tab Cronograma: {len(eventos)} eventos extraídos")
            return eventos
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo tab Cronograma: {e}")
            return []
    
    def extract_complete_details(self):
        """Extraer detalles completos (todos los tabs)"""
        try:
            detalle = {
                'tab_remate': self.extract_tab_remate(),
                'tab_inmuebles': self.extract_tab_inmuebles(), 
                'tab_cronograma': self.extract_tab_cronograma()
            }
            
            logger.info("✅ Detalles completos extraídos")
            return detalle
            
        except Exception as e:
            logger.error(f"❌ Error extrayendo detalles completos: {e}")
            return {}

# ========================================
# CLASE PRINCIPAL DEL SCRAPER
# ========================================

class REMAJUScraperOrganizado:
    """Scraper principal organizado con estructura jerárquica modular"""
    
    def __init__(self):
        self.driver = None
        self.modulo_remates = None
        self.modulo_detalle = None
        self.stats = {
            'start_time': datetime.now(),
            'total_remates': 0,
            'remates_with_details': 0,
            'errors': 0,
            'pages_processed': 0
        }
    
    def setup(self):
        """Configurar el scraper"""
        try:
            self.driver = setup_driver()
            if not self.driver:
                return False
            
            self.modulo_remates = ModuloRemates(self.driver)
            self.modulo_detalle = ModuloDetalle(self.driver)
            
            logger.info("✅ Scraper configurado correctamente")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error configurando scraper: {e}")
            return False
    
    def navigate_to_main_page(self):
        """Navegar a la página principal"""
        try:
            logger.info("🌐 Navegando a REMAJU...")
            self.driver.get(MAIN_URL)
            time.sleep(5)  # Tiempo para CAPTCHA manual si es necesario
            
            # Verificar que cargó correctamente
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            logger.info("✅ Página principal cargada")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error navegando a página principal: {e}")
            return False
    
    def run_complete_extraction(self):
        """Ejecutar extracción completa con estructura jerárquica"""
        try:
            logger.info("🚀 Iniciando extracción completa REMAJU (estructura organizada)")
            
            # Setup inicial
            if not self.setup():
                return self.create_error_result("Error en configuración")
            
            # Navegar a página principal
            if not self.navigate_to_main_page():
                return self.create_error_result("Error navegando a página principal")
            
            # 1. MÓDULO REMATES (Listado)
            logger.info("📋 Extrayendo Módulo Remates...")
            
            modulo_remates_data = {
                'filtros_aplicados': self.modulo_remates.extract_filtros_aplicados(),
                'formulario_filtros': self.modulo_remates.extract_formulario_filtros(),
                'resultados': []
            }
            
            # Extraer resultados del listado
            resultados = self.modulo_remates.extract_resultados()
            modulo_remates_data['resultados'] = resultados
            self.stats['total_remates'] = len(resultados)
            
            # 2. MÓDULO DETALLE (Para remates seleccionados)
            logger.info("🔍 Extrayendo Módulo Detalle...")
            
            detailed_remates = []
            max_details = min(MAX_DETAILS, len(resultados))
            
            for i in range(max_details):
                try:
                    remate = resultados[i]
                    logger.info(f"🔍 Procesando detalle {i+1}/{max_details}: Remate {remate.get('numero_remate')}")
                    
                    # Navegar al detalle
                    if self.modulo_detalle.navigate_to_detail(i):
                        # Extraer detalles completos
                        detalle = self.modulo_detalle.extract_complete_details()
                        
                        complete_remate = {
                            'numero_remate': remate.get('numero_remate'),
                            'basic_info': remate,
                            'detalle': detalle,
                            'extraction_timestamp': datetime.now().isoformat(),
                            'source_url': self.driver.current_url
                        }
                        
                        detailed_remates.append(complete_remate)
                        self.stats['remates_with_details'] += 1
                        
                        logger.info(f"✅ Detalle completo extraído para remate {remate.get('numero_remate')}")
                    
                    # Volver al listado
                    self.modulo_detalle.return_to_listing()
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error procesando detalle {i}: {e}")
                    self.stats['errors'] += 1
                    continue
            
            # Resultado final
            resultado_final = {
                'status': 'success',
                'timestamp': datetime.now().isoformat(),
                'sistema': 'REMAJU',
                'fuente': MAIN_URL,
                'estadisticas': self.generate_stats(),
                'modulo_remates': modulo_remates_data,
                'modulo_detalle_remates': detailed_remates
            }
            
            logger.info("✅ Extracción completa finalizada exitosamente")
            return resultado_final
            
        except Exception as e:
            logger.error(f"❌ Error en extracción completa: {e}")
            return self.create_error_result(f"Error en extracción: {str(e)}")
        
        finally:
            if self.driver:
                self.driver.quit()
    
    def generate_stats(self):
        """Generar estadísticas de la ejecución"""
        end_time = datetime.now()
        duration = (end_time - self.stats['start_time']).total_seconds()
        
        return {
            'duracion_segundos': round(duration, 2),
            'inicio': self.stats['start_time'].isoformat(),
            'fin': end_time.isoformat(),
            'total_remates_listado': self.stats['total_remates'],
            'remates_con_detalle': self.stats['remates_with_details'],
            'paginas_procesadas': self.stats['pages_processed'],
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

# ========================================
# FUNCIÓN PRINCIPAL
# ========================================

def main():
    """Función principal"""
    try:
        logger.info("🎯 Iniciando REMAJU Scraper Organizado...")
        
        # Crear y ejecutar scraper
        scraper = REMAJUScraperOrganizado()
        resultado = scraper.run_complete_extraction()
        
        # Guardar resultados
        output_file = 'remates_result.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 Resultados guardados en: {output_file}")
        
        # Mostrar resumen
        if resultado['status'] == 'success':
            stats = resultado['estadisticas']
            logger.info("🎉 SCRAPING COMPLETADO EXITOSAMENTE")
            logger.info(f"📊 Total remates: {stats['total_remates_listado']}")
            logger.info(f"🔍 Con detalles: {stats['remates_con_detalle']}")
            logger.info(f"⏱️ Duración: {stats['duracion_segundos']} segundos")
            logger.info(f"📈 Tasa éxito: {stats['tasa_exito_detalle']}%")
        else:
            logger.error(f"❌ ERROR: {resultado['error_message']}")
        
        return resultado
        
    except Exception as e:
        logger.error(f"❌ Error en función principal: {e}")
        return {'status': 'error', 'error_message': str(e)}

if __name__ == "__main__":
    result = main()
    
    # Códigos de salida para GitHub Actions
    if result.get('status') == 'error':
        sys.exit(1)
    else:
        sys.exit(0)
