name: REMAJU Scraper

on:
  workflow_dispatch:
    inputs:
      trigger_source:
        description: 'Fuente del trigger (manual, n8n_automated, etc.)'
        required: false
        default: 'manual'
        type: string
      max_details:
        description: 'Máximo número de remates para extraer detalle completo'
        required: false
        default: '5' 
        type: string
      headless:
        description: 'Ejecutar en modo headless'
        required: false
        default: 'true'
        type: choice
        options:
        - 'true'
        - 'false'

  repository_dispatch:
    types: [remaju_scrape]

jobs:
  scrape-remaju:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
      
    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
        cache: 'pip'
        
    - name: Setup Chrome Browser
      uses: browser-actions/setup-chrome@v1
      with:
        chrome-version: 'stable'
        
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        
    - name: Configure environment
      run: |
        echo "PYTHONUNBUFFERED=1" >> $GITHUB_ENV
        echo "MAX_DETAILS=${{ inputs.max_details || '5' }}" >> $GITHUB_ENV
        echo "HEADLESS=${{ inputs.headless || 'true' }}" >> $GITHUB_ENV
        echo "TRIGGER_SOURCE=${{ inputs.trigger_source || github.event.action || 'workflow_dispatch' }}" >> $GITHUB_ENV
        echo "GITHUB_ACTIONS=true" >> $GITHUB_ENV
        
    - name: Display configuration
      run: |
        echo "Configuración de ejecución:"
        echo "  Fuente: ${{ env.TRIGGER_SOURCE }}"
        echo "  Detalles máx: ${{ env.MAX_DETAILS }}"
        echo "  Headless: ${{ env.HEADLESS }}"
        echo "  Runner: ${{ runner.os }}"
        
    - name: Run REMAJU scraper
      id: scraper
      run: |
        echo "Iniciando scraper REMAJU..."
        python scraper.py
        echo "Scraping completado"
        
    - name: Process results
      if: always()
      run: |
        if [ -f remates_result.json ]; then
          echo "Análisis de resultados:"
          python -c "
          import json
          import sys
          
          try:
              with open('remates_result.json', 'r', encoding='utf-8') as f:
                  data = json.load(f)
              
              status = data.get('status', 'unknown')
              print(f'Status: {status}')
              
              if status == 'success':
                  stats = data.get('estadisticas', {})
                  modulo_remates = data.get('modulo_remates', {})
                  modulo_detalle = data.get('modulo_detalle_remates', [])
                  
                  print(f'Estadísticas:')
                  print(f'  Total remates: {stats.get(\"total_remates_listado\", 0)}')
                  print(f'  Remates con detalle: {stats.get(\"remates_con_detalle\", 0)}')
                  print(f'  Duración: {stats.get(\"duracion_segundos\", 0)} segundos')
                  print(f'  Tasa éxito: {stats.get(\"tasa_exito_detalle\", 0)}%')
                  
                  print(f'Módulo Remates:')
                  print(f'  Filtros aplicados: {len(modulo_remates.get(\"filtros_aplicados\", {}))} filtros')
                  print(f'  Elementos formulario: {len(modulo_remates.get(\"formulario_filtros\", {}))} campos')
                  print(f'  Resultados: {len(modulo_remates.get(\"resultados\", []))} remates')
                  
                  print(f'Módulo Detalle:')
                  print(f'  Remates con detalle: {len(modulo_detalle)} remates')
              
              elif status == 'error':
                  print(f'Error: {data.get(\"error_message\", \"Error desconocido\")}')
                  sys.exit(1)
              
              else:
                  print(f'Estado desconocido: {status}')
                  sys.exit(1)
                  
          except Exception as e:
              print(f'Error procesando resultados: {e}')
              sys.exit(1)
          "
        else
          echo "No se encontró archivo de resultados"
          exit 1
        fi
        
    - name: Upload results artifact
      uses: actions/upload-artifact@v4
      if: always()
      with:
        name: remaju-results-${{ github.run_number }}
        path: |
          remates_result.json
        retention-days: 7
        compression-level: 6
        
    - name: Create summary
      if: always()
      run: |
        echo "## REMAJU Scraper - Resumen" >> $GITHUB_STEP_SUMMARY
        echo "" >> $GITHUB_STEP_SUMMARY
        
        if [ -f remates_result.json ]; then
          python -c "
          import json
          import os
          
          with open('remates_result.json', 'r', encoding='utf-8') as f:
              data = json.load(f)
          
          status = data.get('status', 'unknown')
          
          if status == 'success':
              stats = data.get('estadisticas', {})
              
              summary = f'''### Ejecución Exitosa
              
              **Estadísticas:**
              - Total remates: {stats.get('total_remates_listado', 0)}
              - Con detalle: {stats.get('remates_con_detalle', 0)}
              - Duración: {stats.get('duracion_segundos', 0)} seg
              - Tasa éxito: {stats.get('tasa_exito_detalle', 0)}%
              
              **Estructura Modular:**
              - Módulo Remates: Listado + filtros
              - Módulo Detalle: 3 tabs por remate
              
              '''
              
          else:
              summary = f'''### Ejecución Fallida
              
              **Error:** {data.get('error_message', 'Desconocido')}
              '''
          
          with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
              f.write(summary)
          "
        else
          echo "### Sin resultados" >> $GITHUB_STEP_SUMMARY
          echo "No se generó archivo de resultados" >> $GITHUB_STEP_SUMMARY
        fi

    - name: Cleanup
      if: always()
      run: |
        rm -f chromedriver.log
        echo "Cleanup completado"
