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

# Configuración
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://remaju.pj.gob.pe"
MAIN_URL = f"{BASE_URL}/remaju/pages/publico/remateExterno.xhtml"
MAX_DETAILS = int(os.environ.get('MAX_DETAILS', '5'))
HEADLESS = os.environ.get('HEADLESS', 'true').lower() == 'true'

def setup_driver():
    """Configurar driver Chrome"""
    chrome_options = Options()
    if HEADLESS:
        chrome_options.add_argument("--headless=new")
    
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1366,768")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(60)
    return driver

def safe_find_element(driver, by, value, timeout=10, optional=False):
    """Buscar elemento de forma segura"""
    try:
        return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))
    except TimeoutException:
        if not optional:
            logger.warning(f"Elemento no encontrado: {value}")
        return None

def safe_get_text(element, default=""):
    """Obtener texto de elemento de forma segura"""
    try:
        if element:
            return element.get_attribute('textContent') or element.text or default
        return default
    except:
        return default

def clean_text(text):
    """Limpiar texto eliminando espacios extra y saltos de línea"""
    if not text:
        return ""
    return ' '.join(text.strip().split())

def extract_price_info(text):
    """Extraer información de precio de texto"""
    if not text:
        return "", 0.0, ""
    
    # Buscar patrón de precio
    price_patterns = [
        r'(S/\.|USD|\$)\s*([\d,]+\.?\d*)',
        r'([\d,]+\.?\d*)\s*(SOLES|DOLARES)',
        r'S/\.\s*([\d,]+\.?\d*)',
        r'\$\s*([\d,]+\.?\d*)',
        r'([\d,]+\.?\d*)\s*soles'
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if pattern.startswith('(S/'):
                currency = match.group(1)
                amount_str = match.group(2)
            elif 'SOLES' in pattern:
                currency = "S/."
                amount_str = match.group(1)
            elif pattern.startswith('S/'):
                currency = "S/."
                amount_str = match.group(1)
            elif pattern.startswith(r'\$'):
                currency = "USD"
                amount_str = match.group(1)
            else:
                currency = "S/."
                amount_str = match.group(1)
            
            try:
                amount = float(amount_str.replace(',', ''))
                return f"{currency} {amount_str}", amount, currency
            except:
                return text, 0.0, currency
    
    return text, 0.0, ""

class REMAJUScraper:
    def __init__(self):
        self.driver = None
        self.stats = {
            'start_time': datetime.now(),
            'total_remates': 0,
            'remates_with_details': 0,
            'errors': 0
        }
    
    def setup(self):
        """Configurar scraper"""
        try:
            self.driver = setup_driver()
            if not self.driver:
                return False
            logger.info("Scraper configurado correctamente")
            return True
        except Exception as e:
            logger.error(f"Error configurando scraper: {e}")
            return False
    
    def navigate_to_main_page(self):
        """Navegar a página principal"""
        try:
            logger.info("Navegando a REMAJU...")
            self.driver.get(MAIN_URL)
            time.sleep(5)  # Tiempo para carga inicial
            
            # Verificar que cargó
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            logger.info("Página principal cargada")
            return True
        except Exception as e:
            logger.error(f"Error navegando: {e}")
            return False
    
    def extract_filtros_aplicados(self):
        """Extraer filtros aplicados"""
        filtros = {}
        try:
            body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body"))
            
            if "Publicación e Inscripción" in body_text:
                filtros['fase'] = "Publicación e Inscripción"
            
            # Buscar botón limpiar
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
        try:
            # Verificar disponibilidad de campos comunes
            campos = {
                'numero_remate': "//input[contains(@placeholder, 'remate') or contains(@name, 'remate')]",
                'numero_expediente': "//input[contains(@placeholder, 'expediente') or contains(@name, 'expediente')]",
                'precio_base': "//input[contains(@placeholder, 'precio') or contains(@name, 'precio')]",
                'tipo_inmueble': "//select[contains(@name, 'tipo')]",
                'ubicacion': "//select[contains(@name, 'departamento')]",
                'fases': "//select[contains(@name, 'fase')]"
            }
            
            for campo, xpath in campos.items():
                elemento = safe_find_element(self.driver, By.XPATH, xpath, optional=True)
                form_elements[campo] = {'available': bool(elemento)}
            
            # CAPTCHA y botón aplicar
            captcha = safe_find_element(self.driver, By.XPATH, "//img[contains(@src, 'captcha')]", optional=True)
            aplicar = safe_find_element(self.driver, By.XPATH, "//input[@type='submit']", optional=True)
            
            form_elements['captcha'] = {'available': bool(captcha)}
            form_elements['aplicar'] = {'available': bool(aplicar)}
            
        except Exception as e:
            logger.warning(f"Error extrayendo formulario: {e}")
        
        return form_elements
    
    def extract_remate_cards_from_table(self):
        """Extraer tarjetas de remates desde tabla"""
        remates = []
        try:
            # Buscar tabla principal
            table = safe_find_element(self.driver, By.XPATH, "//table[contains(@class, 'dataTable') or .//th[contains(text(), 'Remate')]]")
            
            if not table:
                logger.warning("No se encontró tabla de remates")
                return []
            
            # Obtener filas de datos
            rows = table.find_elements(By.XPATH, ".//tbody/tr")
            logger.info(f"Encontradas {len(rows)} filas en la tabla")
            
            for i, row in enumerate(rows):
                try:
                    cells = row.find_elements(By.XPATH, ".//td")
                    if len(cells) < 3:  # Mínimo esperado
                        continue
                    
                    # Obtener texto de toda la fila
                    row_text = safe_get_text(row)
                    
                    # Extraer número de remate
                    remate_match = re.search(r'(?:remate\s+n[°º]?\s*)?(\d+)', row_text, re.IGNORECASE)
                    numero_remate = remate_match.group(1) if remate_match else f"REMATE_{i+1}"
                    
                    # Convocatoria
                    tipo_convocatoria = ""
                    numero_convocatoria = ""
                    if "PRIMERA" in row_text.upper():
                        tipo_convocatoria = "PRIMERA"
                        numero_convocatoria = "PRIMERA CONVOCATORIA"
                    elif "SEGUNDA" in row_text.upper():
                        tipo_convocatoria = "SEGUNDA"
                        numero_convocatoria = "SEGUNDA CONVOCATORIA"
                    
                    # Extraer precio
                    precio_texto, precio_numerico, moneda = extract_price_info(row_text)
                    
                    # Fechas
                    fecha_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', row_text)
                    hora_match = re.search(r'(\d{1,2}:\d{2})', row_text)
                    
                    # Descripción (buscar texto más largo que no sea fecha/precio)
                    descripcion = ""
                    words = row_text.split()
                    for j in range(len(words)-5):
                        phrase = ' '.join(words[j:j+6])
                        if len(phrase) > 30 and not re.search(r'\d{1,2}/\d{4}|\d+[,.]?\d*', phrase):
                            descripcion = phrase
                            break
                    
                    remate_data = {
                        'numero_remate': numero_remate,
                        'tipo_convocatoria': tipo_convocatoria,
                        'numero_convocatoria': numero_convocatoria,
                        'titulo_card': f"Remate N° {numero_remate}" + (f" - {numero_convocatoria}" if numero_convocatoria else ""),
                        'thumbnail_url': "",
                        'no_disponible': True,
                        'tipo_remate': "Judicial",
                        'ubicacion_corta': "",  # Se extraerá en detalle
                        'fecha_presentacion_oferta': fecha_match.group(1) if fecha_match else "",
                        'hora_presentacion_oferta': hora_match.group(1) if hora_match else "",
                        'descripcion_corta': descripcion[:200],
                        'estado_fase': "Publicación e Inscripción",
                        'precio_base_texto': precio_texto,
                        'precio_base_numerico': precio_numerico,
                        'moneda': moneda,
                        'acciones': {
                            'seguimiento': "",
                            'detalle': "detalle_disponible",
                            'aviso': ""
                        },
                        'card_index': i + 1,
                        'pagina': 1,
                        'posicion_en_pagina': i + 1
                    }
                    
                    remates.append(remate_data)
                    
                except Exception as e:
                    logger.warning(f"Error procesando fila {i}: {e}")
                    continue
            
            self.stats['total_remates'] = len(remates)
            logger.info(f"Extraídos {len(remates)} remates de la tabla")
            return remates
            
        except Exception as e:
            logger.error(f"Error extrayendo remates: {e}")
            return []
    
    def navigate_to_detail(self, card_index):
        """Navegar al detalle de un remate"""
        try:
            # Buscar botones de detalle
            detail_buttons = self.driver.find_elements(By.XPATH, 
                "//button[contains(text(), 'Detalle')] | //input[@value='Detalle'] | //a[contains(text(), 'Detalle')]")
            
            if not detail_buttons or card_index >= len(detail_buttons):
                logger.warning(f"No se encontró botón detalle para índice {card_index}")
                return False
            
            button = detail_buttons[card_index]
            if not (button.is_displayed() and button.is_enabled()):
                return False
            
            # Click
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            time.sleep(0.5)
            self.driver.execute_script("arguments[0].click();", button)
            
            # Esperar carga de detalle
            def detail_loaded(driver):
                text = driver.find_element(By.TAG_NAME, "body").text.lower()
                return any(keyword in text for keyword in ["expediente", "tasación", "partida", "distrito judicial"])
            
            WebDriverWait(self.driver, 15).until(detail_loaded)
            logger.info(f"Navegado al detalle (índice {card_index})")
            return True
            
        except Exception as e:
            logger.warning(f"Error navegando al detalle: {e}")
            return False
    
    def return_to_listing(self):
        """Volver al listado"""
        try:
            back_button = safe_find_element(self.driver, By.XPATH,
                "//button[contains(text(),'Regresar')] | //a[contains(text(),'Regresar')] | //input[@value='Regresar']",
                optional=True)
            
            if back_button and back_button.is_displayed():
                self.driver.execute_script("arguments[0].click();", back_button)
                time.sleep(3)
            else:
                self.driver.back()
                time.sleep(3)
            
            # Esperar que cargue el listado
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
            
        except Exception as e:
            logger.warning(f"Error volviendo al listado: {e}")
    
    def extract_specific_field_value(self, text_lines, field_label, next_line_fallback=True):
        """Extraer valor específico de un campo"""
        for i, line in enumerate(text_lines):
            if field_label.lower() in line.lower():
                # Buscar valor después del label en la misma línea
                parts = line.split(':')
                if len(parts) > 1:
                    value = parts[1].strip()
                    if value and value != field_label:
                        return value
                
                # Si no hay valor en la misma línea, buscar en la siguiente
                if next_line_fallback and i + 1 < len(text_lines):
                    next_value = text_lines[i + 1].strip()
                    if next_value and next_value.lower() != field_label.lower():
                        return next_value
        return ""
    
    def extract_tab_remate_details(self):
        """Extraer detalles del tab Remate"""
        try:
            # Obtener texto completo de la página
            body = self.driver.find_element(By.TAG_NAME, "body")
            full_text = safe_get_text(body)
            lines = [line.strip() for line in full_text.split('\n') if line.strip()]
            
            # Bloque expediente
            expediente = {
                'expediente': self.extract_specific_field_value(lines, "Expediente"),
                'distrito_judicial': self.extract_specific_field_value(lines, "Distrito Judicial"),
                'organo_jurisdiccional': self.extract_specific_field_value(lines, "Órgano Jurisdiccional"),
                'instancia': self.extract_specific_field_value(lines, "Instancia"),
                'juez': self.extract_specific_field_value(lines, "Juez"),
                'especialista': self.extract_specific_field_value(lines, "Especialista"),
                'materia': self.extract_specific_field_value(lines, "Materia"),
                'resolucion': self.extract_specific_field_value(lines, "Resolución"),
                'fecha_resolucion': self.extract_specific_field_value(lines, "Fecha Resolución"),
                'archivo_resolucion_url': ""
            }
            
            # Bloque económico
            economico = {
                'convocatoria': self.extract_specific_field_value(lines, "Convocatoria"),
                'tipo_cambio': self.extract_specific_field_value(lines, "Tipo de Cambio"),
                'tasacion': self.extract_specific_field_value(lines, "Tasación"),
                'precio_base': self.extract_specific_field_value(lines, "Precio Base"),
                'incremento_ofertas': self.extract_specific_field_value(lines, "Incremento entre ofertas"),
                'arancel': self.extract_specific_field_value(lines, "Arancel"),
                'oblaje': self.extract_specific_field_value(lines, "Oblaje"),
                'descripcion_completa': self.extract_specific_field_value(lines, "Descripción")
            }
            
            # Indicadores
            inscritos_text = self.extract_specific_field_value(lines, "N° inscritos")
            num_inscritos = 0
            if inscritos_text:
                match = re.search(r'\d+', inscritos_text)
                num_inscritos = int(match.group()) if match else 0
            
            indicadores = {
                'num_inscritos': num_inscritos,
                'regresar': True
            }
            
            return {
                'bloque_expediente': expediente,
                'bloque_economico': economico,
                'indicadores': indicadores
            }
            
        except Exception as e:
            logger.warning(f"Error extrayendo tab remate: {e}")
            return {}
    
    def extract_tab_inmuebles_details(self):
        """Extraer detalles del tab Inmuebles"""
        try:
            # Intentar hacer clic en tab Inmuebles
            inmuebles_tab = safe_find_element(self.driver, By.XPATH,
                "//a[contains(text(), 'Inmuebles')] | //button[contains(text(), 'Inmuebles')] | //*[@id='inmuebles']",
                optional=True)
            
            if inmuebles_tab and inmuebles_tab.is_displayed():
                self.driver.execute_script("arguments[0].click();", inmuebles_tab)
                time.sleep(2)
            
            # Buscar tabla de inmuebles específicamente
            inmuebles_table = safe_find_element(self.driver, By.XPATH,
                "//table[.//th[contains(text(), 'Partida')] or .//td[contains(text(), 'TIPO INMUEBLE')]]",
                optional=True)
            
            inmuebles = []
            
            if inmuebles_table:
                # Si hay tabla, extraer datos estructurados
                data_rows = inmuebles_table.find_elements(By.XPATH, ".//tbody/tr | .//tr[position()>1]")
                
                for i, row in enumerate(data_rows):
                    try:
                        cells = row.find_elements(By.XPATH, ".//td")
                        if len(cells) >= 4:  # Mínimo esperado
                            inmueble = {
                                'partida_registral': clean_text(safe_get_text(cells[0])) if len(cells) > 0 else "",
                                'tipo_inmueble': clean_text(safe_get_text(cells[1])) if len(cells) > 1 else "",
                                'direccion': clean_text(safe_get_text(cells[2])) if len(cells) > 2 else "",
                                'cargas_gravamenes': clean_text(safe_get_text(cells[3])) if len(cells) > 3 else "",
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
                            
                            # Validar que no sean headers
                            if (inmueble['partida_registral'] and 
                                not any(word in inmueble['partida_registral'].upper() for word in ['PARTIDA', 'TIPO', 'DIRECCIÓN', 'HEADER'])):
                                inmuebles.append(inmueble)
                                
                    except Exception as e:
                        logger.warning(f"Error procesando fila inmueble {i}: {e}")
                        continue
            else:
                # Fallback: extraer de texto general
                body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body"))
                lines = [line.strip() for line in body_text.split('\n') if line.strip()]
                
                inmueble = {
                    'partida_registral': self.extract_specific_field_value(lines, "Partida"),
                    'tipo_inmueble': self.extract_specific_field_value(lines, "Tipo"),
                    'direccion': self.extract_specific_field_value(lines, "Dirección"),
                    'cargas_gravamenes': self.extract_specific_field_value(lines, "Cargas"),
                    'porcentaje_a_rematar': 100.0,
                    'imagenes_refs': {'count': 0, 'urls': []},
                    'orden': 1
                }
                
                if inmueble['partida_registral'] or inmueble['direccion']:
                    inmuebles.append(inmueble)
            
            logger.info(f"Tab Inmuebles: {len(inmuebles)} inmuebles extraídos")
            return inmuebles
            
        except Exception as e:
            logger.warning(f"Error extrayendo tab inmuebles: {e}")
            return []
    
    def extract_tab_cronograma_details(self):
        """Extraer detalles del tab Cronograma"""
        try:
            # Intentar hacer clic en tab Cronograma
            cronograma_tab = safe_find_element(self.driver, By.XPATH,
                "//a[contains(text(), 'Cronograma')] | //button[contains(text(), 'Cronograma')] | //*[@id='cronograma']",
                optional=True)
            
            if cronograma_tab and cronograma_tab.is_displayed():
                self.driver.execute_script("arguments[0].click();", cronograma_tab)
                time.sleep(2)
            
            body_text = safe_get_text(self.driver.find_element(By.TAG_NAME, "body"))
            
            eventos = []
            
            # Buscar eventos específicos con fechas
            eventos_patterns = [
                (r'inscripci[óo]n.*?(\d{1,2}/\d{1,2}/\d{4}).*?(\d{1,2}:\d{2})', 'Inscripción de postores'),
                (r'exhibici[óo]n.*?(\d{1,2}/\d{1,2}/\d{4}).*?(\d{1,2}:\d{2})', 'Exhibición'),
                (r'presentaci[óo]n.*?ofertas.*?(\d{1,2}/\d{1,2}/\d{4}).*?(\d{1,2}:\d{2})', 'Presentación de ofertas'),
                (r'acto.*?remate.*?(\d{1,2}/\d{1,2}/\d{4}).*?(\d{1,2}:\d{2})', 'Acto de remate')
            ]
            
            for i, (pattern, evento_nombre) in enumerate(eventos_patterns):
                match = re.search(pattern, body_text, re.IGNORECASE | re.DOTALL)
                if match:
                    evento = {
                        'hito': evento_nombre,
                        'evento': evento_nombre,
                        'fecha': match.group(1),
                        'hora': match.group(2),
                        'observacion': "",
                        'orden': i + 1,
                        'regresar': True
                    }
                    eventos.append(evento)
            
            # Si no se encuentran patrones específicos, buscar fechas genéricas
            if not eventos:
                fechas_encontradas = re.findall(r'(\d{1,2}/\d{1,2}/\d{4})', body_text)
                horas_encontradas = re.findall(r'(\d{1,2}:\d{2})', body_text)
                
                for i, fecha in enumerate(fechas_encontradas[:4]):  # Máximo 4 eventos
                    hora = horas_encontradas[i] if i < len(horas_encontradas) else ""
                    evento = {
                        'hito': f"Evento {i+1}",
                        'evento': f"Evento {i+1}",
                        'fecha': fecha,
                        'hora': hora,
                        'observacion': "",
                        'orden': i + 1,
                        'regresar': True
                    }
                    eventos.append(evento)
            
            logger.info(f"Tab Cronograma: {len(eventos)} eventos extraídos")
            return eventos
            
        except Exception as e:
            logger.warning(f"Error extrayendo tab cronograma: {e}")
            return []
    
    def extract_complete_details(self):
        """Extraer detalles completos de todos los tabs"""
        try:
            detalle = {
                'tab_remate': self.extract_tab_remate_details(),
                'tab_inmuebles': self.extract_tab_inmuebles_details(),
                'tab_cronograma': self.extract_tab_cronograma_details()
            }
            return detalle
        except Exception as e:
            logger.error(f"Error extrayendo detalles completos: {e}")
            return {}
    
    def run_extraction(self):
        """Ejecutar extracción completa - solo primera página"""
        try:
            logger.info("Iniciando extracción REMAJU - Primera página solamente")
            
            if not self.setup():
                return self.create_error_result("Error en configuración")
            
            if not self.navigate_to_main_page():
                return self.create_error_result("Error navegando a página principal")
            
            # Módulo Remates
            logger.info("Extrayendo módulo Remates...")
            modulo_remates = {
                'filtros_aplicados': self.extract_filtros_aplicados(),
                'formulario_filtros': self.extract_formulario_filtros(),
                'resultados': self.extract_remate_cards_from_table()
            }
            
            # Módulo Detalle
            logger.info("Extrayendo módulo Detalle...")
            detailed_remates = []
            resultados = modulo_remates['resultados']
            max_details = min(MAX_DETAILS, len(resultados))
            
            for i in range(max_details):
                try:
                    remate = resultados[i]
                    logger.info(f"Procesando detalle {i+1}/{max_details}: Remate {remate.get('numero_remate')}")
                    
                    if self.navigate_to_detail(i):
                        detalle = self.extract_complete_details()
                        
                        complete_remate = {
                            'numero_remate': remate.get('numero_remate'),
                            'basic_info': remate,
                            'detalle': detalle,
                            'extraction_timestamp': datetime.now().isoformat(),
                            'source_url': self.driver.current_url
                        }
                        
                        detailed_remates.append(complete_remate)
                        self.stats['remates_with_details'] += 1
                        
                        logger.info(f"Detalle completo extraído para remate {remate.get('numero_remate')}")
                    
                    self.return_to_listing()
                    
                except Exception as e:
                    logger.warning(f"Error procesando detalle {i}: {e}")
                    self.stats['errors'] += 1
                    continue
            
            # Resultado final
            resultado = {
                'status': 'success',
                'timestamp': datetime.now().isoformat(),
                'sistema': 'REMAJU',
                'fuente': MAIN_URL,
                'estadisticas': self.generate_stats(),
                'modulo_remates': modulo_remates,
                'modulo_detalle_remates': detailed_remates
            }
            
            logger.info("Extracción completada exitosamente")
            return resultado
            
        except Exception as e:
            logger.error(f"Error en extracción: {e}")
            return self.create_error_result(str(e))
        
        finally:
            if self.driver:
                self.driver.quit()
    
    def generate_stats(self):
        """Generar estadísticas"""
        end_time = datetime.now()
        duration = (end_time - self.stats['start_time']).total_seconds()
        
        return {
            'duracion_segundos': round(duration, 2),
            'inicio': self.stats['start_time'].isoformat(),
            'fin': end_time.isoformat(),
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
        logger.info("Iniciando REMAJU Scraper - Primera página")
        
        scraper = REMAJUScraper()
        resultado = scraper.run_extraction()
        
        # Guardar resultados
        output_file = 'remates_result.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Resultados guardados en: {output_file}")
        
        # Mostrar resumen
        if resultado['status'] == 'success':
            stats = resultado['estadisticas']
            logger.info(f"COMPLETADO - {stats['total_remates_listado']} remates, {stats['remates_con_detalle']} con detalle")
            print(f"total_remates={stats['total_remates_listado']}")
            print(f"remates_con_detalle={stats['remates_con_detalle']}")
            print("status=success")
        else:
            logger.error(f"ERROR: {resultado['error_message']}")
            print("status=error")
        
        return resultado
        
    except Exception as e:
        logger.error(f"Error en función principal: {e}")
        print("status=error")
        return {'status': 'error', 'error_message': str(e)}

if __name__ == "__main__":
    result = main()
    sys.exit(0 if result.get('status') == 'success' else 1)
