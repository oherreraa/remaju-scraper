import json
import os
import time
import logging
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_driver():
    """Configurar Chrome driver optimizado"""
    chrome_options = Options()
    
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1366,768')
    
    # Optimizaciones de velocidad
    chrome_options.add_argument('--disable-images')
    chrome_options.add_argument('--disable-plugins')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-web-security')
    
    # Anti-detección básico
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36')
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def extract_remate_tab_info(driver):
    """Extraer información de la pestaña REMATE"""
    remate_data = {
        # Información del expediente
        "expediente": "",
        "distrito_judicial": "",
        "organo_jurisdiccional": "",
        "instancia": "",
        "juez": "",
        "especialista": "",
        "materia": "",
        "resolucion": "",
        "fecha_resolucion": "",
        "archivo_resolucion": "",
        
        # Información del remate
        "convocatoria": "",
        "tipo_cambio": "",
        "tasacion": "",
        "precio_base": "",
        "precio_base_numerico": 0,
        "precio_base_moneda": "",
        "incremento_ofertas": "",
        "arancel": "",
        "oblaje": "",
        "descripcion_completa": "",
        "num_inscritos": ""
    }
    
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        
        # Procesar líneas buscando patrones específicos
        for i, line in enumerate(lines):
            
            # Información del expediente
            if line == "Expediente" and i + 1 < len(lines):
                remate_data["expediente"] = lines[i + 1]
            elif line == "Distrito Judicial" and i + 1 < len(lines):
                remate_data["distrito_judicial"] = lines[i + 1]
            elif line == "Órgano Jurisdiccional" and i + 1 < len(lines):
                remate_data["organo_jurisdiccional"] = lines[i + 1]
            elif line == "Instancia" and i + 1 < len(lines):
                remate_data["instancia"] = lines[i + 1]
            elif line == "Juez" and i + 1 < len(lines):
                remate_data["juez"] = lines[i + 1]
            elif line == "Especialista" and i + 1 < len(lines):
                remate_data["especialista"] = lines[i + 1]
            elif line == "Materia" and i + 1 < len(lines):
                remate_data["materia"] = lines[i + 1]
            elif line == "Resolución" and i + 1 < len(lines):
                remate_data["resolucion"] = lines[i + 1]
            elif line == "Fecha Resolución" and i + 1 < len(lines):
                remate_data["fecha_resolucion"] = lines[i + 1]
            elif line == "Archivo" and i + 1 < len(lines):
                remate_data["archivo_resolucion"] = lines[i + 1]
            
            # Información del remate
            elif line == "Convocatoria" and i + 1 < len(lines):
                remate_data["convocatoria"] = lines[i + 1]
            elif line == "Tipo Cambio" and i + 1 < len(lines):
                remate_data["tipo_cambio"] = lines[i + 1]
            elif line == "Tasación" and i + 1 < len(lines):
                remate_data["tasacion"] = lines[i + 1]
            elif line == "Precio Base" and i + 1 < len(lines):
                precio_base = lines[i + 1]
                remate_data["precio_base"] = precio_base
                
                # Extraer valor numérico y moneda
                if "$" in precio_base:
                    remate_data["precio_base_moneda"] = "USD"
                    numbers = re.findall(r'[\d,]+\.?\d*', precio_base.replace(',', ''))
                    if numbers:
                        try:
                            remate_data["precio_base_numerico"] = float(numbers[0])
                        except:
                            pass
                elif "S/" in precio_base:
                    remate_data["precio_base_moneda"] = "PEN"
                    numbers = re.findall(r'[\d,]+\.?\d*', precio_base.replace(',', ''))
                    if numbers:
                        try:
                            remate_data["precio_base_numerico"] = float(numbers[0])
                        except:
                            pass
            
            elif line == "Incremento entre ofertas" and i + 1 < len(lines):
                remate_data["incremento_ofertas"] = lines[i + 1]
            elif line == "Arancel" and i + 1 < len(lines):
                remate_data["arancel"] = lines[i + 1]
            elif line == "Oblaje" and i + 1 < len(lines):
                remate_data["oblaje"] = lines[i + 1]
            elif line == "Descripción" and i + 1 < len(lines):
                remate_data["descripcion_completa"] = lines[i + 1]
            elif line == "N° inscritos" and i + 1 < len(lines):
                remate_data["num_inscritos"] = lines[i + 1]
        
        logger.info(f"✅ Pestaña REMATE: Expediente {remate_data['expediente']}, Precio {remate_data['precio_base']}")
        
    except Exception as e:
        logger.error(f"Error en extract_remate_tab_info: {e}")
    
    return remate_data

def extract_inmuebles_tab_info(driver):
    """Extraer información de la pestaña INMUEBLES"""
    inmuebles_data = {
        "inmueble_distrito_judicial": "",
        "inmueble_departamento": "",
        "inmueble_provincia": "",
        "inmueble_distrito": "",
        "inmueble_partida_registral": "",
        "inmueble_tipo": "",
        "inmueble_direccion": "",
        "inmueble_cargas_gravamenes": "",
        "inmueble_porcentaje_rematar": "",
        "inmueble_imagenes": ""
    }
    
    try:
        # Intentar hacer clic en la pestaña Inmuebles
        try:
            inmuebles_tab = driver.find_element(By.XPATH, "//a[contains(text(), 'Inmuebles') or contains(@href, 'inmuebles') or contains(@onclick, 'inmuebles')]")
            driver.execute_script("arguments[0].click();", inmuebles_tab)
            time.sleep(3)
            logger.info("✅ Navegó a pestaña Inmuebles")
        except:
            logger.warning("⚠️ No se pudo hacer clic en pestaña Inmuebles, extrayendo de página actual")
        
        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        
        # Buscar información específica de inmuebles
        for i, line in enumerate(lines):
            if line == "Distrito Judicial" and i + 1 < len(lines):
                inmuebles_data["inmueble_distrito_judicial"] = lines[i + 1]
            elif line == "Departamento" and i + 1 < len(lines):
                inmuebles_data["inmueble_departamento"] = lines[i + 1]
            elif line == "Provincia" and i + 1 < len(lines):
                inmuebles_data["inmueble_provincia"] = lines[i + 1]
            elif line == "Distrito" and i + 1 < len(lines):
                inmuebles_data["inmueble_distrito"] = lines[i + 1]
        
        # Buscar información de tabla de inmuebles
        try:
            table_text = driver.find_element(By.TAG_NAME, "body").text
            
            # Extraer partida registral
            partida_match = re.search(r'(P?\d{8,})', table_text)
            if partida_match:
                inmuebles_data["inmueble_partida_registral"] = partida_match.group(1)
            
            # Extraer tipo de inmueble
            tipos_inmuebles = ['CASA', 'DEPARTAMENTO', 'TERRENO', 'LOCAL', 'OFICINA', 'EDIFICIO']
            for tipo in tipos_inmuebles:
                if tipo in table_text.upper():
                    inmuebles_data["inmueble_tipo"] = tipo
                    break
            
            # Extraer dirección (buscar línea larga con ubicación)
            direccion_matches = re.findall(r'[A-Z][A-Z\s\.,]+MZ[^\.]+\.', table_text)
            if direccion_matches:
                inmuebles_data["inmueble_direccion"] = direccion_matches[0].strip()
            
            # Extraer cargas y gravámenes
            cargas_section = re.search(r'HIPOTECA.*?ESCRITURA[^\.]*\.', table_text, re.DOTALL)
            if cargas_section:
                inmuebles_data["inmueble_cargas_gravamenes"] = cargas_section.group(0)
            
            # Extraer porcentaje a rematar
            porcentaje_match = re.search(r'(\d+\s*%)', table_text)
            if porcentaje_match:
                inmuebles_data["inmueble_porcentaje_rematar"] = porcentaje_match.group(1)
            
        except Exception as e:
            logger.debug(f"Error extrayendo tabla de inmuebles: {e}")
        
        logger.info(f"✅ Pestaña INMUEBLES: {inmuebles_data['inmueble_tipo']} en {inmuebles_data['inmueble_distrito']}")
        
    except Exception as e:
        logger.error(f"Error en extract_inmuebles_tab_info: {e}")
    
    return inmuebles_data

def extract_cronograma_tab_info(driver):
    """Extraer información de la pestaña CRONOGRAMA"""
    cronograma_data = {
        "cronograma_fases": [],
        "cronograma_texto_completo": ""
    }
    
    try:
        # Intentar hacer clic en la pestaña Cronograma
        try:
            cronograma_tab = driver.find_element(By.XPATH, "//a[contains(text(), 'Cronograma') or contains(@href, 'cronograma') or contains(@onclick, 'cronograma')]")
            driver.execute_script("arguments[0].click();", cronograma_tab)
            time.sleep(3)
            logger.info("✅ Navegó a pestaña Cronograma")
        except:
            logger.warning("⚠️ No se pudo hacer clic en pestaña Cronograma, extrayendo de página actual")
        
        page_text = driver.find_element(By.TAG_NAME, "body").text
        cronograma_data["cronograma_texto_completo"] = page_text
        
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        
        # Extraer fases del cronograma
        fases = []
        
        for line in lines:
            # Buscar líneas que empiecen con número (fases)
            if re.match(r'^\d+[A-Za-z]', line):
                fase = {
                    "linea_completa": line
                }
                
                # Extraer número de fase
                numero_match = re.match(r'^(\d+)', line)
                if numero_match:
                    fase["numero"] = numero_match.group(1)
                
                # Extraer nombre de fase
                partes = line.split()
                if len(partes) > 1:
                    fase["fase_nombre"] = partes[1]
                
                # Extraer fechas (formato dd/mm/yyyy)
                fechas = re.findall(r'\d{2}/\d{2}/\d{4}', line)
                if len(fechas) >= 2:
                    fase["fecha_inicio"] = fechas[0]
                    fase["fecha_fin"] = fechas[1]
                
                # Extraer horas
                horas = re.findall(r'\d{2}:\d{2}:\d{2}\s*[AP]M', line)
                if len(horas) >= 2:
                    fase["hora_inicio"] = horas[0]
                    fase["hora_fin"] = horas[1]
                
                fases.append(fase)
        
        cronograma_data["cronograma_fases"] = fases
        
        logger.info(f"✅ Pestaña CRONOGRAMA: {len(fases)} fases extraídas")
        
    except Exception as e:
        logger.error(f"Error en extract_cronograma_tab_info: {e}")
    
    return cronograma_data

def extract_detail_page_info(driver):
    """Extraer toda la información de la página de detalle con las 3 pestañas"""
    detail_data = {}
    
    try:
        # Esperar a que cargue completamente
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        logger.info("📋 Extrayendo información de pestaña REMATE")
        
        # PESTAÑA 1: REMATE (información principal)
        remate_info = extract_remate_tab_info(driver)
        detail_data.update(remate_info)
        
        # PESTAÑA 2: INMUEBLES
        logger.info("🏠 Navegando a pestaña INMUEBLES")
        inmuebles_info = extract_inmuebles_tab_info(driver)
        detail_data.update(inmuebles_info)
        
        # PESTAÑA 3: CRONOGRAMA
        logger.info("📅 Navegando a pestaña CRONOGRAMA")
        cronograma_info = extract_cronograma_tab_info(driver)
        detail_data.update(cronograma_info)
        
        logger.info("✅ Información completa extraída de las 3 pestañas")
        return detail_data
        
    except Exception as e:
        logger.error(f"Error extrayendo información de detalle: {e}")
        return detail_data

def extract_basic_remate_info_only(driver):
    """Extraer solo información básica de remates SIN navegar a detalles"""
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        
        remates_info = []
        
        # Buscar patrones de remates
        for i, line in enumerate(lines):
            if "remate n°" in line.lower() and "convocatoria" in line.lower():
                
                # Extraer información básica
                numero_match = re.search(r'remate n°?\s*(\d+)', line.lower())
                if numero_match:
                    remate_numero = numero_match.group(1)
                    
                    remate_info = {
                        "numero": remate_numero,
                        "numero_remate": line,
                        "line_index": i,
                        "tipo_convocatoria": "PRIMERA" if "primera" in line.lower() else 
                                           "SEGUNDA" if "segunda" in line.lower() else 
                                           "TERCERA" if "tercera" in line.lower() else ""
                    }
                    
                    remates_info.append(remate_info)
                    logger.info(f"📋 Remate {remate_numero} encontrado")
        
        logger.info(f"📄 Total remates básicos: {len(remates_info)}")
        return remates_info
        
    except Exception as e:
        logger.error(f"Error en extract_basic_remate_info_only: {e}")
        return []

def find_and_click_detail_by_position_improved(driver, remate_info):
    """Estrategia mejorada para encontrar botón detalle"""
    try:
        remate_numero = remate_info['numero']
        logger.info(f"🎯 Buscando detalle para remate {remate_numero}")
        
        # Esperar un poco para asegurar que la página esté completamente cargada
        time.sleep(2)
        
        # Obtener todos los botones de detalle con espera explícita
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(text(), 'Detalle')]"))
            )
        except:
            logger.warning("⚠️ No se pudieron encontrar botones Detalle con espera explícita")
        
        # Múltiples estrategias para encontrar botones
        detail_buttons = []
        
        button_selectors = [
            "//a[contains(text(), 'Detalle')]",
            "//input[@value='Detalle']", 
            "//button[contains(text(), 'Detalle')]",
            "//span[contains(text(), 'Detalle')]/parent::*",
            "//*[@onclick and contains(@onclick, 'detalle')]"
        ]
        
        for selector in button_selectors:
            try:
                buttons = driver.find_elements(By.XPATH, selector)
                detail_buttons.extend(buttons)
            except:
                continue
        
        # Remover duplicados
        detail_buttons = list(set(detail_buttons))
        logger.info(f"🔍 Total botones Detalle únicos encontrados: {len(detail_buttons)}")
        
        if not detail_buttons:
            logger.error(f"❌ No se encontraron botones Detalle para remate {remate_numero}")
            return False
        
        # Estrategia 1: Por cercanía al número del remate
        try:
            for button in detail_buttons:
                try:
                    # Buscar el contexto del botón
                    parent_container = button.find_element(By.XPATH, "./ancestor::*[contains(text(), '{}')][1]".format(remate_numero))
                    
                    if parent_container:
                        logger.info(f"✅ Botón detalle encontrado por cercanía para remate {remate_numero}")
                        
                        # Hacer scroll y clic
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                        time.sleep(2)
                        
                        try:
                            button.click()
                        except:
                            driver.execute_script("arguments[0].click();", button)
                        
                        time.sleep(5)
                        
                        # Verificar navegación
                        current_url = driver.current_url
                        if current_url != "https://remaju.pj.gob.pe/remaju/pages/publico/remateExterno.xhtml":
                            logger.info(f"✅ Navegación exitosa por cercanía")
                            return True
                
                except Exception as e:
                    continue
        
        except Exception as e:
            logger.debug(f"Estrategia cercanía falló: {e}")
        
        # Estrategia 2: Probar botones secuencialmente
        logger.info(f"🔄 Probando todos los botones secuencialmente...")
        
        for idx, button in enumerate(detail_buttons):
            try:
                if button.is_displayed() and button.is_enabled():
                    logger.info(f"   Probando botón {idx + 1}/{len(detail_buttons)}")
                    
                    # Guardar URL actual
                    original_url = driver.current_url
                    
                    # Hacer scroll y clic
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                    time.sleep(1)
                    
                    try:
                        button.click()
                    except:
                        driver.execute_script("arguments[0].click();", button)
                    
                    time.sleep(4)
                    
                    # Verificar si navegó
                    new_url = driver.current_url
                    if new_url != original_url:
                        # Verificar que es página de detalle
                        page_text = driver.find_element(By.TAG_NAME, "body").text
                        if "expediente" in page_text.lower() or "tasación" in page_text.lower():
                            logger.info(f"✅ NAVEGACIÓN EXITOSA con botón {idx + 1}")
                            return True
                        else:
                            logger.warning(f"⚠️ Navegó pero no es página de detalle, regresando...")
                            driver.back()
                            time.sleep(3)
                
            except Exception as e:
                logger.debug(f"Error con botón {idx + 1}: {e}")
                continue
        
        logger.error(f"❌ No se pudo navegar a detalle de remate {remate_numero}")
        return False
        
    except Exception as e:
        logger.error(f"Error en find_and_click_detail_by_position_improved: {e}")
        return False

def navigate_to_next_page_improved(driver, target_page):
    """Navegación mejorada a siguiente página"""
    try:
        logger.info(f"🔄 Navegando a página {target_page}")
        
        # Esperar a que la página esté lista
        time.sleep(2)
        
        # Estrategia 1: Buscar enl
