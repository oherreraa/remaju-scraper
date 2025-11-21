#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REMAJU Scraper - Versión Actualizada con Estructura Modular
Sistema completo de scraping para remates judiciales del Poder Judicial del Perú

Estructura:
1. Módulo "Remates" - Listado principal con filtros y resultados
2. Módulo "Detalle" - Información detallada por remate (3 tabs)
   2.1. Tab "Remate" - Datos generales
   2.2. Tab "Inmuebles" - Lista de bienes  
   2.3. Tab "Cronograma" - Eventos del remate

Autor: Oscar (ENGIE Energía Perú S.A.)
Fecha: Noviembre 2025
"""

import json
import os
import sys
import time
import logging
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Optional, Union

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.action_chains import ActionChains

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('remaju_scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class REMAJUScraperAdvanced:
    """Scraper avanzado para el sistema REMAJU con arquitectura modular"""
    
    def __init__(self, headless=True, max_wait=30):
        self.base_url = "https://remaju.pj.gob.pe"
        self.main_url = f"{self.base_url}/remaju/pages/publico/remateExterno.xhtml"
        self.headless = headless
        self.max_wait = max_wait
        self.driver = None
        self.wait = None
        
        # Configuración para GitHub Actions
        self.is_github_actions = os.environ.get('GITHUB_ACTIONS') == 'true'
        
        # Estadísticas
        self.stats = {
            'start_time': datetime.now(),
            'total_remates': 0,
            'remates_with_details': 0,
            'errors': 0,
            'pages_processed': 0
        }
        
        # Cache para evitar reprocessamiento
        self.processed_remates = set()

    def setup_driver(self):
        """Configurar el driver de Chrome optimizado"""
        try:
            chrome_options = Options()
            
            if self.headless:
                chrome_options.add_argument('--headless=new')
            
            # Opciones optimizadas para GitHub Actions y estabilidad
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-plugins')
            chrome_options.add_argument('--disable-images')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Optimizaciones de rendimiento
            chrome_options.add_argument('--disable-background-timer-throttling')
            chrome_options.add_argument('--disable-backgrounding-occluded-windows')
            chrome_options.add_argument('--disable-renderer-backgrounding')
            chrome_options.add_argument('--memory-pressure-off')
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(60)
            self.wait = WebDriverWait(self.driver, self.max_wait)
            
            logger.info("✅ Driver configurado correctamente")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error configurando driver: {e}")
            return False

    def safe_find_element(self, by, value, timeout=10, optional=False):
        """Buscar elemento de forma segura con reintentos"""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return element
        except TimeoutException:
            if not optional:
                logger.warning(f"⚠️ Elemento no encontrado: {by}={value}")
            return None
        except Exception as e:
            logger.error(f"❌ Error buscando elemento {by}={value}: {e}")
            return None

    def safe_find_elements(self, by, value, timeout=10):
        """Buscar múltiples elementos de forma segura"""
        try:
            self.wait.until(EC.presence_of_element_located((by, value)))
            return self.driver.find_elements(by, value)
        except TimeoutException:
            logger.warning(f"⚠️ Elementos no encontrados: {by}={value}")
            return []
        except Exception as e:
            logger.error(f"❌ Error buscando elementos {by}={value}: {e}")
            return []

    def get_text_safe(self, element, default=""):
        """Extraer texto de elemento de forma segura"""
        try:
            if element:
                text = element.get_attribute('textContent') or element.text or ""
                return text.strip()
            return default
        except Exception as e:
            logger.warning(f"⚠️ Error obteniendo texto: {e}")
            return default

    def get_attribute_safe(self, element, attribute, default=""):
        """Obtener atributo de elemento de forma segura"""
        try:
            if element:
                return element.get_attribute(attribute) or default
            return default
        except Exception as e:
            logger.warning(f"⚠️ Error obteniendo atributo {attribute}: {e}")
            return default

    def navigate_to_main_page(self):
        """Navegar a la página principal de REMAJU"""
        try:
            logger.info("🌐 Navegando a REMAJU...")
            self.driver.get(self.main_url)
            
            # Esperar a que cargue la página
            time.sleep(3)
            
            # Verificar que la página cargó correctamente
            page_title = self.driver.title
            logger.info(f"📄 Título de página: {page_title}")
            
            # Esperar a que aparezcan los elementos principales
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error navegando a página principal: {e}")
            return False

    def extract_filters_applied(self):
        """Extraer filtros aplicados actualmente"""
        filters = {}
        
        try:
            # Buscar chips de filtros aplicados
            filter_chips = self.safe_find_elements(By.CSS_SELECTOR, ".filter-chip, .ui-selectcheckboxmenu-token")
            
            for chip in filter_chips:
                filter_text = self.get_text_safe(chip)
                if filter_text and "fase" in filter_text.lower():
                    filters['fase'] = filter_text
                    
            # Buscar botón eliminar filtros
            clear_filters_btn = self.safe_find_element(By.CSS_SELECTOR, 
                "a[title*='Limpiar'], button[title*='Limpiar'], .clear-filters", 
                optional=True)
            
            if clear_filters_btn:
                filters['eliminar_filtros'] = True
                
            logger.info(f"📋 Filtros aplicados encontrados: {filters}")
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo filtros aplicados: {e}")
            
        return filters

    def extract_filter_form_elements(self):
        """Extraer elementos del formulario de filtros"""
        form_elements = {}
        
        try:
            # Mapeo de campos del formulario
            field_mappings = {
                'numero_remate': ['input[name*="remate"]', 'input[placeholder*="remate"]', '#numeroRemate'],
                'numero_expediente': ['input[name*="expediente"]', 'input[placeholder*="expediente"]', '#numeroExpediente'],
                'precio_base': ['input[name*="precio"]', 'input[placeholder*="precio"]', '#precioBase'],
                'tipo_inmueble': ['select[name*="tipo"]', 'select[name*="inmueble"]', '#tipoInmueble'],
                'ubicacion': ['input[name*="ubicacion"]', 'select[name*="ubicacion"]', '#ubicacion'],
                'fases': ['select[name*="fase"]', 'select[name*="estado"]', '#fases']
            }
            
            for field_name, selectors in field_mappings.items():
                for selector in selectors:
                    element = self.safe_find_element(By.CSS_SELECTOR, selector, optional=True)
                    if element:
                        form_elements[field_name] = {
                            'element_type': element.tag_name,
                            'name': self.get_attribute_safe(element, 'name'),
                            'id': self.get_attribute_safe(element, 'id'),
                            'placeholder': self.get_attribute_safe(element, 'placeholder'),
                            'available': True
                        }
                        break
                else:
                    form_elements[field_name] = {'available': False}
            
            # Buscar CAPTCHA
            captcha_element = self.safe_find_element(By.CSS_SELECTOR, 
                ".captcha, img[src*='captcha'], #captcha", optional=True)
            form_elements['captcha'] = {'available': bool(captcha_element)}
            
            # Buscar botón aplicar
            apply_button = self.safe_find_element(By.CSS_SELECTOR,
                "button[type='submit'], input[type='submit'], .btn-search, .aplicar", optional=True)
            form_elements['aplicar'] = {'available': bool(apply_button)}
            
            logger.info(f"📝 Elementos del formulario: {len(form_elements)} encontrados")
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo elementos del formulario: {e}")
            
        return form_elements

    def extract_remate_card_data(self, card_element):
        """Extraer datos de una tarjeta de remate individual"""
        try:
            remate_data = {}
            
            # Número de remate
            numero_elem = card_element.find_element(By.CSS_SELECTOR, 
                ".numero-remate, .remate-number, strong:first-child") if card_element else None
            remate_data['numero_remate'] = self.get_text_safe(numero_elem)
            
            # Número y tipo de convocatoria
            convocatoria_elem = card_element.find_element(By.CSS_SELECTOR,
                ".convocatoria, .tipo-convocatoria") if card_element else None
            convocatoria_text = self.get_text_safe(convocatoria_elem)
            
            # Extraer tipo (PRIMERA, SEGUNDA, etc.)
            if "PRIMERA" in convocatoria_text.upper():
                remate_data['tipo_convocatoria'] = "PRIMERA"
            elif "SEGUNDA" in convocatoria_text.upper():
                remate_data['tipo_convocatoria'] = "SEGUNDA"
            else:
                remate_data['tipo_convocatoria'] = convocatoria_text
                
            remate_data['numero_convocatoria'] = convocatoria_text
            
            # Título de la tarjeta
            title_elem = card_element.find_element(By.CSS_SELECTOR,
                ".titulo, .card-title, h3, h4") if card_element else None
            remate_data['titulo_card'] = self.get_text_safe(title_elem)
            
            # Imagen thumbnail
            img_elem = card_element.find_element(By.CSS_SELECTOR, "img") if card_element else None
            if img_elem:
                img_src = self.get_attribute_safe(img_elem, 'src')
                if img_src and 'no-disponible' not in img_src.lower():
                    remate_data['thumbnail_url'] = urljoin(self.base_url, img_src)
                    remate_data['no_disponible'] = False
                else:
                    remate_data['no_disponible'] = True
            else:
                remate_data['no_disponible'] = True
                
            # Tipo de remate
            tipo_elem = card_element.find_element(By.CSS_SELECTOR,
                ".tipo-remate, .tipo") if card_element else None
            remate_data['tipo_remate'] = self.get_text_safe(tipo_elem)
            
            # Ubicación corta
            ubicacion_elem = card_element.find_element(By.CSS_SELECTOR,
                ".ubicacion, .direccion") if card_element else None
            remate_data['ubicacion_corta'] = self.get_text_safe(ubicacion_elem)
            
            # Fecha y hora de presentación de oferta
            fecha_elem = card_element.find_element(By.CSS_SELECTOR,
                ".fecha-presentacion, .fecha-oferta") if card_element else None
            fecha_text = self.get_text_safe(fecha_elem)
            
            # Parsear fecha y hora
            if fecha_text:
                # Intentar extraer fecha y hora con regex
                fecha_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', fecha_text)
                hora_match = re.search(r'(\d{1,2}:\d{2})', fecha_text)
                
                remate_data['fecha_presentacion_oferta'] = fecha_match.group(1) if fecha_match else fecha_text
                remate_data['hora_presentacion_oferta'] = hora_match.group(1) if hora_match else ""
            
            # Descripción corta
            desc_elem = card_element.find_element(By.CSS_SELECTOR,
                ".descripcion, .descripcion-corta, p") if card_element else None
            remate_data['descripcion_corta'] = self.get_text_safe(desc_elem)
            
            # Estado/fase
            estado_elem = card_element.find_element(By.CSS_SELECTOR,
                ".estado, .fase, .estado-fase") if card_element else None
            remate_data['estado_fase'] = self.get_text_safe(estado_elem)
            
            # Precio base
            precio_elem = card_element.find_element(By.CSS_SELECTOR,
                ".precio, .precio-base") if card_element else None
            precio_text = self.get_text_safe(precio_elem)
            
            if precio_text:
                remate_data['precio_base_texto'] = precio_text
                
                # Extraer moneda y valor numérico
                moneda_match = re.search(r'(S/\.|USD|\$|€)', precio_text)
                remate_data['moneda'] = moneda_match.group(1) if moneda_match else "S/."
                
                # Extraer número
                numero_match = re.search(r'[\d,\.]+', precio_text.replace(',', ''))
                if numero_match:
                    try:
                        remate_data['precio_base_numerico'] = float(numero_match.group(0))
                    except:
                        remate_data['precio_base_numerico'] = 0
                else:
                    remate_data['precio_base_numerico'] = 0
            
            # Enlaces de acción
            acciones = {}
            
            # Buscar enlaces de seguimiento, detalle y aviso
            action_links = card_element.find_elements(By.CSS_SELECTOR, "a, button") if card_element else []
            
            for link in action_links:
                link_text = self.get_text_safe(link).lower()
                href = self.get_attribute_safe(link, 'href')
                onclick = self.get_attribute_safe(link, 'onclick')
                
                if 'seguimiento' in link_text:
                    acciones['seguimiento'] = href or onclick
                elif 'detalle' in link_text or 'ver' in link_text:
                    acciones['detalle'] = href or onclick
                elif 'aviso' in link_text:
                    acciones['aviso'] = href or onclick
                    
            remate_data['acciones'] = acciones
            
            return remate_data
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo datos de tarjeta: {e}")
            return {}

    def extract_remate_listings(self):
        """Extraer listado completo de remates con paginación"""
        all_remates = []
        page_num = 1
        max_pages = int(os.environ.get('MAX_PAGES', '10'))  # Límite de páginas
        
        try:
            while True:
                logger.info(f"📄 Procesando página {page_num}...")
                
                # Esperar a que cargue el contenido
                time.sleep(2)
                
                # Buscar tarjetas de remates
                remate_cards = self.safe_find_elements(By.CSS_SELECTOR, 
                    ".remate-card, .card-remate, .resultado-item, .item-remate")
                
                if not remate_cards:
                    # Intentar selectores alternativos
                    remate_cards = self.safe_find_elements(By.CSS_SELECTOR,
                        "div[class*='remate'], div[class*='card'], .list-item")
                
                if not remate_cards:
                    logger.warning(f"⚠️ No se encontraron tarjetas en página {page_num}")
                    break
                
                logger.info(f"📋 Encontradas {len(remate_cards)} tarjetas en página {page_num}")
                
                # Extraer datos de cada tarjeta
                for i, card in enumerate(remate_cards):
                    try:
                        remate_data = self.extract_remate_card_data(card)
                        if remate_data and remate_data.get('numero_remate'):
                            remate_data['pagina'] = page_num
                            remate_data['posicion_en_pagina'] = i + 1
                            all_remates.append(remate_data)
                            
                    except Exception as e:
                        logger.warning(f"⚠️ Error procesando tarjeta {i}: {e}")
                        continue
                
                self.stats['pages_processed'] = page_num
                
                # Verificar si hay siguiente página
                if max_pages > 0 and page_num >= max_pages:
                    logger.info(f"🔄 Límite de páginas alcanzado: {max_pages}")
                    break
                
                # Buscar y hacer clic en "siguiente página"
                next_button = self.safe_find_element(By.CSS_SELECTOR,
                    ".ui-paginator-next, .next-page, a[title*='Siguiente'], button[title*='Siguiente']",
                    optional=True, timeout=5)
                
                if not next_button or 'disabled' in (next_button.get_attribute('class') or ''):
                    logger.info(f"🏁 No hay más páginas después de la página {page_num}")
                    break
                
                try:
                    # Hacer clic en siguiente página
                    self.driver.execute_script("arguments[0].click();", next_button)
                    page_num += 1
                    
                    # Esperar a que cambie la página
                    time.sleep(3)
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error navegando a página siguiente: {e}")
                    break
            
            self.stats['total_remates'] = len(all_remates)
            logger.info(f"✅ Listado completo: {len(all_remates)} remates en {page_num} páginas")
            
            return all_remates
            
        except Exception as e:
            logger.error(f"❌ Error extrayendo listado de remates: {e}")
            return all_remates

    def navigate_to_remate_detail(self, remate_data):
        """Navegar al detalle de un remate específico"""
        try:
            detalle_link = remate_data.get('acciones', {}).get('detalle')
            
            if not detalle_link:
                logger.warning(f"⚠️ No hay enlace de detalle para remate {remate_data.get('numero_remate')}")
                return False
                
            # Si es onclick, ejecutar JavaScript
            if detalle_link.startswith('javascript:') or 'javascript:' in detalle_link:
                self.driver.execute_script(detalle_link.replace('javascript:', ''))
            else:
                # Si es URL directa, navegar
                if not detalle_link.startswith('http'):
                    detalle_link = urljoin(self.base_url, detalle_link)
                self.driver.get(detalle_link)
            
            # Esperar a que cargue la página de detalle
            time.sleep(3)
            
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Error navegando al detalle: {e}")
            return False

    def extract_tab_remate_data(self):
        """Extraer datos del Tab 'Remate' (datos generales)"""
        tab_data = {}
        
        try:
            # Activar tab si es necesario
            remate_tab = self.safe_find_element(By.CSS_SELECTOR,
                "a[href*='remate'], .tab-remate, li[data-tab='remate']", optional=True)
            if remate_tab:
                remate_tab.click()
                time.sleep(1)
            
            # Bloque expediente/juzgado
            expediente_data = {}
            
            field_mappings = {
                'expediente': ['.expediente', '.numero-expediente', 'span[id*="expediente"]'],
                'distrito_judicial': ['.distrito-judicial', '.distrito', 'span[id*="distrito"]'],
                'organo_jurisdiccional': ['.organo-jurisdiccional', '.juzgado', 'span[id*="organo"]'],
                'instancia': ['.instancia', 'span[id*="instancia"]'],
                'juez': ['.juez', '.magistrado', 'span[id*="juez"]'],
                'especialista': ['.especialista', 'span[id*="especialista"]'],
                'materia': ['.materia', 'span[id*="materia"]'],
                'resolucion': ['.resolucion', 'span[id*="resolucion"]'],
                'fecha_resolucion': ['.fecha-resolucion', 'span[id*="fecha"]'],
                'archivo_resolucion_url': ['a[href*="resolucion"]', 'a[href*="archivo"]']
            }
            
            for field_name, selectors in field_mappings.items():
                for selector in selectors:
                    element = self.safe_find_element(By.CSS_SELECTOR, selector, optional=True)
                    if element:
                        if field_name == 'archivo_resolucion_url':
                            href = self.get_attribute_safe(element, 'href')
                            if href:
                                expediente_data[field_name] = urljoin(self.base_url, href)
                        else:
                            expediente_data[field_name] = self.get_text_safe(element)
                        break
                else:
                    expediente_data[field_name] = ""
            
            tab_data['bloque_expediente'] = expediente_data
            
            # Bloque económico/convocatoria
            economico_data = {}
            
            economico_mappings = {
                'convocatoria': ['.convocatoria', 'span[id*="convocatoria"]'],
                'tipo_cambio': ['.tipo-cambio', 'span[id*="cambio"]'],
                'tasacion': ['.tasacion', 'span[id*="tasacion"]'],
                'precio_base': ['.precio-base', 'span[id*="precio"]'],
                'incremento_ofertas': ['.incremento', 'span[id*="incremento"]'],
                'arancel': ['.arancel', 'span[id*="arancel"]'],
                'oblaje': ['.oblaje', 'span[id*="oblaje"]'],
                'descripcion_completa': ['.descripcion-completa', '.descripcion-detallada', 'textarea[id*="descripcion"]']
            }
            
            for field_name, selectors in economico_mappings.items():
                for selector in selectors:
                    element = self.safe_find_element(By.CSS_SELECTOR, selector, optional=True)
                    if element:
                        economico_data[field_name] = self.get_text_safe(element)
                        break
                else:
                    economico_data[field_name] = ""
            
            tab_data['bloque_economico'] = economico_data
            
            # Indicadores
            indicadores_data = {}
            
            # Número de inscritos
            inscritos_elem = self.safe_find_element(By.CSS_SELECTOR,
                '.num-inscritos, .inscritos, span[id*="inscritos"]', optional=True)
            inscritos_text = self.get_text_safe(inscritos_elem)
            
            if inscritos_text:
                # Extraer número
                numero_match = re.search(r'\d+', inscritos_text)
                indicadores_data['num_inscritos'] = int(numero_match.group(0)) if numero_match else 0
            else:
                indicadores_data['num_inscritos'] = 0
            
            # Botón regresar
            regresar_btn = self.safe_find_element(By.CSS_SELECTOR,
                '.btn-regresar, .regresar, button[value*="Regresar"]', optional=True)
            indicadores_data['regresar'] = bool(regresar_btn)
            
            tab_data['indicadores'] = indicadores_data
            
            logger.info("✅ Datos del tab 'Remate' extraídos")
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo tab Remate: {e}")
            
        return tab_data

    def extract_tab_inmuebles_data(self):
        """Extraer datos del Tab 'Inmuebles' (lista de bienes)"""
        tab_data = []
        
        try:
            # Activar tab si es necesario
            inmuebles_tab = self.safe_find_element(By.CSS_SELECTOR,
                "a[href*='inmuebles'], .tab-inmuebles, li[data-tab='inmuebles']", optional=True)
            if inmuebles_tab:
                inmuebles_tab.click()
                time.sleep(2)
            
            # Buscar tabla o lista de inmuebles
            inmuebles_containers = self.safe_find_elements(By.CSS_SELECTOR,
                ".inmueble-item, .bien-item, tr[class*='inmueble'], .lista-inmuebles .item")
            
            if not inmuebles_containers:
                # Buscar en tabla estándar
                inmuebles_containers = self.safe_find_elements(By.CSS_SELECTOR, "tbody tr")
            
            logger.info(f"📋 Encontrados {len(inmuebles_containers)} inmuebles")
            
            for i, container in enumerate(inmuebles_containers):
                try:
                    inmueble_data = {}
                    
                    # Partida registral
                    partida_elem = container.find_element(By.CSS_SELECTOR,
                        ".partida-registral, .partida, td:nth-child(1)") if container else None
                    inmueble_data['partida_registral'] = self.get_text_safe(partida_elem)
                    
                    # Tipo de inmueble
                    tipo_elem = container.find_element(By.CSS_SELECTOR,
                        ".tipo-inmueble, .tipo, td:nth-child(2)") if container else None
                    inmueble_data['tipo_inmueble'] = self.get_text_safe(tipo_elem)
                    
                    # Dirección
                    direccion_elem = container.find_element(By.CSS_SELECTOR,
                        ".direccion, .ubicacion, td:nth-child(3)") if container else None
                    inmueble_data['direccion'] = self.get_text_safe(direccion_elem)
                    
                    # Cargas y gravámenes
                    cargas_elem = container.find_element(By.CSS_SELECTOR,
                        ".cargas-gravamenes, .cargas, td:nth-child(4)") if container else None
                    inmueble_data['cargas_gravamenes'] = self.get_text_safe(cargas_elem)
                    
                    # Porcentaje a rematar
                    porcentaje_elem = container.find_element(By.CSS_SELECTOR,
                        ".porcentaje-rematar, .porcentaje, td:nth-child(5)") if container else None
                    porcentaje_text = self.get_text_safe(porcentaje_elem)
                    
                    # Extraer número del porcentaje
                    if porcentaje_text:
                        porcentaje_match = re.search(r'(\d+(?:\.\d+)?)%?', porcentaje_text)
                        inmueble_data['porcentaje_a_rematar'] = float(porcentaje_match.group(1)) if porcentaje_match else 100.0
                    else:
                        inmueble_data['porcentaje_a_rematar'] = 100.0
                    
                    # Imágenes (contador/referencias)
                    imagenes_links = container.find_elements(By.CSS_SELECTOR, "a[href*='imagen'], img") if container else []
                    
                    if imagenes_links:
                        inmueble_data['imagenes_refs'] = {
                            'count': len(imagenes_links),
                            'urls': [urljoin(self.base_url, img.get_attribute('href') or img.get_attribute('src'))
                                    for img in imagenes_links if img.get_attribute('href') or img.get_attribute('src')]
                        }
                    else:
                        inmueble_data['imagenes_refs'] = {'count': 0, 'urls': []}
                    
                    inmueble_data['orden'] = i + 1
                    tab_data.append(inmueble_data)
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error procesando inmueble {i}: {e}")
                    continue
            
            logger.info(f"✅ Datos del tab 'Inmuebles' extraídos: {len(tab_data)} items")
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo tab Inmuebles: {e}")
            
        return tab_data

    def extract_tab_cronograma_data(self):
        """Extraer datos del Tab 'Cronograma' (eventos del remate)"""
        tab_data = []
        
        try:
            # Activar tab si es necesario
            cronograma_tab = self.safe_find_element(By.CSS_SELECTOR,
                "a[href*='cronograma'], .tab-cronograma, li[data-tab='cronograma']", optional=True)
            if cronograma_tab:
                cronograma_tab.click()
                time.sleep(2)
            
            # Buscar tabla de cronograma
            cronograma_rows = self.safe_find_elements(By.CSS_SELECTOR,
                ".cronograma-item, .evento-item, tr[class*='cronograma'], tbody tr")
            
            logger.info(f"📋 Encontrados {len(cronograma_rows)} eventos en cronograma")
            
            for i, row in enumerate(cronograma_rows):
                try:
                    evento_data = {}
                    
                    # Hito/evento
                    hito_elem = row.find_element(By.CSS_SELECTOR,
                        ".hito, .evento, .tipo-evento, td:nth-child(1)") if row else None
                    evento_data['hito'] = self.get_text_safe(hito_elem)
                    evento_data['evento'] = evento_data['hito']  # Alias
                    
                    # Fecha
                    fecha_elem = row.find_element(By.CSS_SELECTOR,
                        ".fecha, .fecha-evento, td:nth-child(2)") if row else None
                    evento_data['fecha'] = self.get_text_safe(fecha_elem)
                    
                    # Hora
                    hora_elem = row.find_element(By.CSS_SELECTOR,
                        ".hora, .hora-evento, td:nth-child(3)") if row else None
                    evento_data['hora'] = self.get_text_safe(hora_elem)
                    
                    # Observación
                    obs_elem = row.find_element(By.CSS_SELECTOR,
                        ".observacion, .observaciones, .notas, td:nth-child(4)") if row else None
                    evento_data['observacion'] = self.get_text_safe(obs_elem)
                    
                    evento_data['orden'] = i + 1
                    
                    if evento_data['hito'] or evento_data['fecha']:  # Solo agregar si tiene contenido
                        tab_data.append(evento_data)
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error procesando evento {i}: {e}")
                    continue
            
            # Buscar botón regresar en cronograma
            regresar_btn = self.safe_find_element(By.CSS_SELECTOR,
                '.btn-regresar, .regresar, button[value*="Regresar"]', optional=True)
            
            if regresar_btn:
                for evento in tab_data:
                    evento['regresar'] = True
            
            logger.info(f"✅ Datos del tab 'Cronograma' extraídos: {len(tab_data)} eventos")
            
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo tab Cronograma: {e}")
            
        return tab_data

    def extract_complete_remate_details(self, remate_data):
        """Extraer detalles completos de un remate (todos los tabs)"""
        complete_details = {
            'numero_remate': remate_data.get('numero_remate'),
            'basic_info': remate_data,
            'detalle': {}
        }
        
        try:
            # Navegar al detalle
            if not self.navigate_to_remate_detail(remate_data):
                return None
            
            logger.info(f"🔍 Extrayendo detalles completos del remate {remate_data.get('numero_remate')}")
            
            # Extraer datos de cada tab
            complete_details['detalle']['tab_remate'] = self.extract_tab_remate_data()
            complete_details['detalle']['tab_inmuebles'] = self.extract_tab_inmuebles_data()
            complete_details['detalle']['tab_cronograma'] = self.extract_tab_cronograma_data()
            
            # Agregar metadatos
            complete_details['extraction_timestamp'] = datetime.now().isoformat()
            complete_details['source_url'] = self.driver.current_url
            
            self.stats['remates_with_details'] += 1
            logger.info(f"✅ Detalles completos extraídos para remate {remate_data.get('numero_remate')}")
            
            return complete_details
            
        except Exception as e:
            logger.error(f"❌ Error extrayendo detalles completos: {e}")
            self.stats['errors'] += 1
            return None

    def run_complete_extraction(self):
        """Ejecutar extracción completa del sistema REMAJU"""
        try:
            logger.info("🚀 Iniciando extracción completa de REMAJU...")
            
            # Configurar driver
            if not self.setup_driver():
                return self.create_error_result("Error configurando driver")
            
            # Navegar a página principal
            if not self.navigate_to_main_page():
                return self.create_error_result("Error navegando a página principal")
            
            # Extraer información del módulo principal
            module_remates_data = {
                'filtros_aplicados': self.extract_filters_applied(),
                'formulario_filtros': self.extract_filter_form_elements(),
                'resultados': []
            }
            
            # Extraer listado de remates
            remates_list = self.extract_remate_listings()
            module_remates_data['resultados'] = remates_list
            
            # Determinar cuántos remates extraer en detalle
            max_details = int(os.environ.get('MAX_DETAILS', '5'))  # Limitar por rendimiento
            
            if max_details > 0 and remates_list:
                logger.info(f"🔍 Extrayendo detalles de {min(max_details, len(remates_list))} remates...")
                
                detailed_remates = []
                
                for i, remate in enumerate(remates_list[:max_details]):
                    try:
                        logger.info(f"🔍 Procesando detalle {i+1}/{min(max_details, len(remates_list))}: {remate.get('numero_remate')}")
                        
                        complete_details = self.extract_complete_remate_details(remate)
                        if complete_details:
                            detailed_remates.append(complete_details)
                        
                        # Regresar al listado principal después de cada detalle
                        self.navigate_to_main_page()
                        time.sleep(2)
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Error procesando detalle {i}: {e}")
                        self.stats['errors'] += 1
                        continue
            else:
                detailed_remates = []
            
            # Consolidar resultados finales
            final_result = {
                'status': 'success',
                'timestamp': datetime.now().isoformat(),
                'sistema': 'REMAJU',
                'fuente': 'https://remaju.pj.gob.pe',
                'estadisticas': self.generate_stats(),
                'modulo_remates': module_remates_data,
                'modulo_detalle_remates': detailed_remates
            }
            
            logger.info(f"✅ Extracción completa finalizada exitosamente")
            logger.info(f"📊 Estadísticas finales: {self.generate_stats()}")
            
            return final_result
            
        except Exception as e:
            logger.error(f"❌ Error en extracción completa: {e}")
            return self.create_error_result(f"Error en extracción completa: {str(e)}")
        
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
        """Crear resultado de error estandarizado"""
        return {
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'error_message': error_message,
            'estadisticas': self.generate_stats(),
            'modulo_remates': {'resultados': []},
            'modulo_detalle_remates': []
        }

def main():
    """Función principal para ejecución"""
    try:
        logger.info("🎯 Iniciando REMAJU Scraper Avanzado...")
        
        # Configuración desde variables de entorno
        headless = os.environ.get('HEADLESS', 'true').lower() == 'true'
        max_wait = int(os.environ.get('MAX_WAIT', '30'))
        
        # Crear y ejecutar scraper
        scraper = REMAJUScraperAdvanced(headless=headless, max_wait=max_wait)
        result = scraper.run_complete_extraction()
        
        # Guardar resultados
        output_file = 'remates_result.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 Resultados guardados en: {output_file}")
        
        # Imprimir resumen
        if result['status'] == 'success':
            stats = result['estadisticas']
            logger.info(f"🎉 ÉXITO - {stats['total_remates_listado']} remates, {stats['remates_con_detalle']} con detalle")
        else:
            logger.error(f"❌ ERROR - {result['error_message']}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error en función principal: {e}")
        return {
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'error_message': str(e)
        }

if __name__ == "__main__":
    result = main()
    
    # Salir con código de error si falló
    if result.get('status') == 'error':
        sys.exit(1)
    else:
        sys.exit(0)
