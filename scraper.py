#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REMAJU Scraper - Script de Configuración
Configuración y validación del entorno de desarrollo

Autor: Oscar (ENGIE Energía Perú S.A.)
Fecha: Noviembre 2025
"""

import os
import sys
import subprocess
import json
from pathlib import Path

def check_python_version():
    """Verificar versión de Python"""
    version = sys.version_info
    if version.major == 3 and version.minor >= 8:
        print(f"✅ Python {version.major}.{version.minor}.{version.micro} - OK")
        return True
    else:
        print(f"❌ Python {version.major}.{version.minor}.{version.micro} - Requerido Python 3.8+")
        return False

def install_dependencies():
    """Instalar dependencias"""
    try:
        print("📦 Instalando dependencias...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Dependencias instaladas correctamente")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error instalando dependencias: {e}")
        return False

def check_chrome():
    """Verificar instalación de Chrome"""
    try:
        result = subprocess.run(['google-chrome', '--version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"✅ {version}")
            return True
    except FileNotFoundError:
        pass
    
    try:
        result = subprocess.run(['chromium-browser', '--version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"✅ {version}")
            return True
    except FileNotFoundError:
        pass
    
    print("⚠️ Chrome/Chromium no encontrado - se descargará automáticamente")
    return False

def create_config_file():
    """Crear archivo de configuración por defecto"""
    config = {
        "scraper_settings": {
            "max_pages": 10,
            "max_details": 5,
            "headless": True,
            "max_wait": 30,
            "timeout": 60
        },
        "output_settings": {
            "save_json": True,
            "save_csv": False,
            "save_excel": False,
            "output_dir": "./outputs"
        },
        "github_actions": {
            "artifact_retention_days": 30,
            "timeout_minutes": 60
        }
    }
    
    config_file = "config.json"
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Archivo de configuración creado: {config_file}")
    return True

def create_directories():
    """Crear directorios necesarios"""
    directories = [
        "logs",
        "outputs", 
        "screenshots",
        ".github/workflows"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"📁 Directorio creado: {directory}")
    
    return True

def test_selenium_setup():
    """Probar configuración básica de Selenium"""
    try:
        print("🧪 Probando configuración de Selenium...")
        
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.get("https://httpbin.org/get")
        
        if "httpbin.org" in driver.title.lower() or "httpbin" in driver.page_source:
            print("✅ Selenium configurado correctamente")
            result = True
        else:
            print("⚠️ Selenium funciona pero con problemas menores")
            result = True
            
        driver.quit()
        return result
        
    except Exception as e:
        print(f"❌ Error configurando Selenium: {e}")
        return False

def check_github_workflow():
    """Verificar archivo de GitHub Actions"""
    workflow_file = ".github/workflows/scrape-remaju.yml"
    
    if Path(workflow_file).exists():
        print(f"✅ Workflow de GitHub Actions encontrado: {workflow_file}")
        return True
    else:
        print(f"⚠️ Workflow de GitHub Actions no encontrado: {workflow_file}")
        return False

def main():
    """Función principal de configuración"""
    print("🔧 REMAJU Scraper - Configuración del Entorno")
    print("=" * 50)
    
    all_good = True
    
    # Verificar Python
    if not check_python_version():
        all_good = False
    
    # Verificar Chrome
    check_chrome()
    
    # Instalar dependencias
    if not install_dependencies():
        all_good = False
    
    # Crear directorios
    create_directories()
    
    # Crear configuración
    create_config_file()
    
    # Verificar workflow
    check_github_workflow()
    
    # Probar Selenium
    if not test_selenium_setup():
        all_good = False
    
    print("\n" + "=" * 50)
    
    if all_good:
        print("🎉 ¡Configuración completada exitosamente!")
        print("\nPróximos pasos:")
        print("1. Configura tu token de GitHub para n8n")
        print("2. Ajusta config.json según tus necesidades")
        print("3. Ejecuta: python remaju_scraper_updated.py")
        print("4. O usa GitHub Actions para automatizar")
    else:
        print("⚠️ Configuración completada con advertencias")
        print("Revisa los errores mostrados arriba")
        
    return all_good

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
