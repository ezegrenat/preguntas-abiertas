import csv
import os
import time
import re
import random  # Para generar retrasos aleatorios
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementClickInterceptedException,
    StaleElementReferenceException
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- Configuración de Parámetros ---

# URL base del sitio web (asegúrate de que termine con '/')
URL_BASE = 'https://encuestas-finales.exactas.uba.ar/'

# URL de la página de "Materias"
MATERIAS_URL = urljoin(URL_BASE, 'mates.html')

# Ruta y nombre del archivo CSV donde se guardarán los resultados finales
ARCHIVO_CSV_RESULTADOS = 'resultados_encuestas.csv'

# Encabezados del CSV final
ENCABEZADOS_CSV = ['Cuatrimestre', 'Departamento', 'URL_Departamento', 'Materia', 'URL_Materia', 'Turno_ID', 'Comentario']

# --- Variables Globales para Contar Pausas y Tiempo Total ---
total_sleep_time = 0  # En segundos

# --- Funciones Auxiliares ---

def configurar_driver():
    """
    Configura el WebDriver de Selenium para Chrome utilizando webdriver-manager.
    :return: Instancia del WebDriver.
    """
    options = ChromeOptions()
    options.headless = True  # Ejecutar en modo headless (sin interfaz gráfica)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")  # Establecer tamaño de ventana

    # Opcional: Rotar User-Agent para simular diferentes navegadores
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)\
        Chrome/58.0.3029.110 Safari/537.3",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0",
        # Agrega más agentes de usuario según sea necesario
    ]
    user_agent = random.choice(USER_AGENTS)
    options.add_argument(f'user-agent={user_agent}')

    # Crear una instancia de Service con ChromeDriverManager
    service = Service(ChromeDriverManager().install())

    # Inicializar el WebDriver de Chrome con el servicio y las opciones
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(30)  # Timeout para carga de páginas
    return driver

def extraer_materias_pagina(driver):
    """
    Extrae las materias de la página actual de "Materias".
    :param driver: Instancia del WebDriver.
    :return: Lista de diccionarios con 'Materia' y 'URL_Materia'.
    """
    materias = []
    try:
        # Esperar hasta que la lista de materias esté presente
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//ul[@class='list']"))
        )
        # Encontrar todos los elementos de la lista
        ul_list = driver.find_element(By.XPATH, "//ul[@class='list']")
        items = ul_list.find_elements(By.TAG_NAME, 'li')
        for item in items:
            a_tag = item.find_element(By.TAG_NAME, 'a')
            nombre_materia = a_tag.text.strip()
            href_materia = urljoin(URL_BASE, a_tag.get_attribute('href'))
            materias.append({
                'Materia': nombre_materia,
                'URL_Materia': href_materia
            })
        print(f"  [+] Se han extraído {len(materias)} materias en la página actual.")
    except NoSuchElementException:
        print("  [!] No se encontró la lista de materias.")
    except TimeoutException:
        print("  [!] Tiempo de espera agotado al buscar la lista de materias.")
    return materias

def manejar_paginacion_materias(driver):
    """
    Maneja la paginación en la página de "Materias" y extrae todas las materias de todas las páginas.
    :param driver: Instancia del WebDriver.
    """
    global total_sleep_time
    pagina_actual = 0  # Iniciar en 0 para mates.html#l_mats_0
    comentarios_extraidos = set()  # Para evitar duplicados

    # Determinar el número total de páginas si es posible
    total_paginas = obtener_total_paginas(driver)
    if total_paginas is None:
        # Si no se puede determinar, establecer un número alto para evitar loops infinitos
        total_paginas = 1000

    while pagina_actual < total_paginas:
        print(f"\nProcesando página {pagina_actual + 1} de materias.")
        # Construir la URL con el fragmento hash
        pagina_url = f"{MATERIAS_URL}#l_mats_{pagina_actual}"
        driver.get(pagina_url)
        print(f"  [>] Navegando a: {pagina_url}")
        # Esperar a que la página se cargue
        time.sleep(random.uniform(2, 4))
        total_sleep_time += 3

        # Extraer materias de la página actual
        materias = extraer_materias_pagina(driver)

        for materia in materias:
            materia_url = materia['URL_Materia']
            nombre_materia = materia['Materia']
            print(f"    Procesando Materia: {nombre_materia} - {materia_url}")
            try:
                # Navegar a la página de la materia
                driver.get(materia_url)
                # Extraer información de la materia y comentarios
                extraer_info_materia_y_comentarios(driver, materia_url, nombre_materia, comentarios_extraidos)
            except Exception as e:
                print(f"    [!] Excepción al procesar la materia: {materia_url} - {e}")
            # Pausa aleatoria entre 2 y 5 segundos
            sleep_time = random.uniform(2, 5)
            print(f"  [>] Pausando por {int(sleep_time)} segundos antes de procesar la siguiente materia.")
            time.sleep(sleep_time)
            total_sleep_time += sleep_time

        # Incrementar el contador de página
        pagina_actual += 1

    print("  [*] Se han procesado todas las páginas de materias.")

def obtener_total_paginas(driver):
    """
    Obtiene el número total de páginas en la paginación de materias.
    :param driver: Instancia del WebDriver.
    :return: Número total de páginas o None si no se puede determinar.
    """
    try:
        # Buscar el div de paginación
        paginacion_div = driver.find_element(By.XPATH, "//div[@class='head']")
        enlaces_paginacion = paginacion_div.find_elements(By.XPATH, ".//a[contains(@onclick, 'lst')]")
        numeros_paginas = []
        for enlace in enlaces_paginacion:
            onclick_attr = enlace.get_attribute('onclick')
            match = re.search(r"lst\('mats',\s*(\d+)\)", onclick_attr)
            if match:
                pagina_num = int(match.group(1)) + 1  # Sumamos 1 porque el índice comienza en 0
                numeros_paginas.append(pagina_num)
        total_paginas = max(numeros_paginas) if numeros_paginas else None
        if total_paginas:
            print(f"  [*] Número total de páginas de materias: {total_paginas}")
        else:
            print("  [!] No se pudo determinar el número total de páginas.")
        return total_paginas
    except Exception as e:
        print(f"  [!] Error al obtener el número total de páginas: {e}")
        return None

def extraer_info_materia_y_comentarios(driver, materia_url, nombre_materia, comentarios_extraidos):
    """
    Extrae la información de la materia y sus comentarios.
    :param driver: Instancia del WebDriver.
    :param materia_url: URL de la materia actual.
    :param nombre_materia: Nombre de la materia actual.
    :param comentarios_extraidos: Set para almacenar comentarios ya extraídos y evitar duplicados.
    """
    global total_sleep_time

    # Extraer Departamento
    try:
        departamento_element = driver.find_element(By.XPATH, "//b[contains(text(), 'Departamento:')]")
        departamento_link = departamento_element.find_element(By.XPATH, "following-sibling::a[1]")
        departamento_nombre = departamento_link.text.strip()
        departamento_url = urljoin(URL_BASE, departamento_link.get_attribute('href'))
    except NoSuchElementException:
        departamento_nombre = ''
        departamento_url = ''
    print(f"      Departamento: {departamento_nombre}")

    # Extraer filas de cuatrimestres y comentarios
    try:
        filas = driver.find_elements(By.XPATH, "//table[@class='inline']//tr[starts-with(@id, 'u')]")
        print(f"      Encontrados {len(filas)} cuatrimestres para la materia.")
        for fila in filas:
            try:
                # Extraer Cuatrimestre
                cuatrimestre = fila.find_element(By.XPATH, "./td[1]").text.strip()
                # Extraer enlace de comentarios
                comentarios_link = fila.find_element(By.XPATH, ".//a[contains(@onclick, 'pbca(this,')]")
                onclick_attr = comentarios_link.get_attribute('onclick')
                turno_id_match = re.search(r'pbca\(this,\s*(\d+)\)', onclick_attr)
                if turno_id_match:
                    turno_id = turno_id_match.group(1)
                else:
                    turno_id = ''
                    print("        [!] No se pudo extraer el Turno ID.")

                # Extraer número de comentarios
                comentarios_text = comentarios_link.text.strip()
                num_comentarios_match = re.search(r'ver (\d+) comentarios?', comentarios_text)
                if num_comentarios_match:
                    num_comentarios = int(num_comentarios_match.group(1))
                else:
                    num_comentarios = 0

                print(f"        Cuatrimestre: {cuatrimestre}, Turno ID: {turno_id}, Comentarios Reportados: {num_comentarios}")

                if num_comentarios > 0:
                    # Hacer clic para mostrar los comentarios
                    driver.execute_script("arguments[0].scrollIntoView();", comentarios_link)
                    comentarios_link.click()
                    # Esperar 1 segundo para que los comentarios comiencen a cargarse
                    time.sleep(1)
                    total_sleep_time += 1

                    # Construir el ID correcto del tr que contiene los comentarios
                    materia_id_match = re.search(r'm(\d+)\.html', os.path.basename(materia_url))
                    if materia_id_match:
                        materia_id = materia_id_match.group(1)
                    else:
                        materia_id = ''
                        print("          [!] No se pudo extraer el Materia ID.")

                    tr_comentarios_id = f"trcxm{materia_id}u{turno_id}"
                    print(f"          Buscando el div de comentarios con ID: {tr_comentarios_id}")

                    try:
                        # Esperar a que el div de comentarios esté presente y visible
                        WebDriverWait(driver, 10).until(
                            EC.visibility_of_element_located((By.ID, tr_comentarios_id))
                        )
                        # Añadir una pausa adicional para asegurar que todos los comentarios carguen
                        time.sleep(1)
                        total_sleep_time += 1

                        comentarios_tr = driver.find_element(By.ID, tr_comentarios_id)
                        # Extraer todos los divs con clase 'cm' dentro de 'comentarios_tr'
                        comentarios_divs = comentarios_tr.find_elements(By.XPATH, ".//div[@class='cm']")
                        print(f"          [+] Encontrados {len(comentarios_divs)} comentarios para Turno ID: {turno_id}")

                        # Verificar que el número de comentarios extraídos coincide con el reportado
                        if len(comentarios_divs) != num_comentarios:
                            print(f"          [!] ERROR: Número de comentarios extraídos ({len(comentarios_divs)}) no coincide con el reportado ({num_comentarios}).")
                            # Lanzar una excepción para manejar la discrepancia
                            raise ValueError(f"Discrepancia en comentarios para Turno ID: {turno_id}")

                        comentarios_escritos = 0  # Contador de comentarios escritos para este cuatrimestre
                        for comentario_div in comentarios_divs:
                            try:
                                # Extraer el texto del comentario
                                # Nota: Comentario_div ya es el div con clase 'cm', no necesita buscar otro 'div.cm' dentro
                                comentario_texto = comentario_div.text.strip()
                                # Crear una clave única para el comentario
                                comentario_key = (materia_url, turno_id, comentario_texto)
                                if comentario_key not in comentarios_extraidos:
                                    resultado = {
                                        'Cuatrimestre': cuatrimestre,
                                        'Departamento': departamento_nombre,
                                        'URL_Departamento': departamento_url,
                                        'Materia': nombre_materia,
                                        'URL_Materia': materia_url,
                                        'Turno_ID': turno_id,
                                        'Comentario': comentario_texto
                                    }
                                    # Guardar en CSV inmediatamente
                                    guardar_en_csv_final(ARCHIVO_CSV_RESULTADOS, [resultado], ENCABEZADOS_CSV)
                                    comentarios_extraidos.add(comentario_key)
                                    comentarios_escritos += 1
                                else:
                                    print("            [!] Comentario duplicado encontrado, omitiendo.")
                            except NoSuchElementException:
                                print(f"            [!] No se encontró el div 'cm' para Turno ID: {turno_id}.")
                                continue
                        print(f"          [✔] Comentarios escritos en CSV para Turno ID: {turno_id}: {comentarios_escritos}")
                    except TimeoutException:
                        print(f"          [!] Tiempo de espera agotado al cargar comentarios para Turno ID: {turno_id}.")
                    except NoSuchElementException:
                        print(f"          [!] No se encontró el div de comentarios para Turno ID: {turno_id}.")
                    except ValueError as ve:
                        print(f"          [!] {ve}")
                        # Dependiendo de la necesidad, puedes decidir continuar o detener el script
                        # raise ve  # Descomenta para detener el script
                    except Exception as e:
                        print(f"          [!] Error inesperado al extraer comentarios para Turno ID: {turno_id} - {e}")

                    # Hacer clic nuevamente para ocultar los comentarios
                    comentarios_link.click()
                    print(f"          [>] Comentarios ocultados para Turno ID: {turno_id}.")

                    # Pausa aleatoria entre 1 y 3 segundos
                    sleep_time = random.uniform(1, 3)
                    print(f"          [>] Pausando por {int(sleep_time)} segundos antes de continuar.")
                    time.sleep(sleep_time)
                    total_sleep_time += sleep_time
                else:
                    # No hay comentarios, pero guardar registro
                    resultado = {
                        'Cuatrimestre': cuatrimestre,
                        'Departamento': departamento_nombre,
                        'URL_Departamento': departamento_url,
                        'Materia': nombre_materia,
                        'URL_Materia': materia_url,
                        'Turno_ID': turno_id,
                        'Comentario': ''
                    }
                    # Guardar en CSV inmediatamente
                    guardar_en_csv_final(ARCHIVO_CSV_RESULTADOS, [resultado], ENCABEZADOS_CSV)
                    print(f"        [✔] Materia sin comentarios. Registro guardado.")
            except Exception as e:
                print(f"        [!] Error al procesar una fila de cuatrimestre: {e}")
                continue
    except NoSuchElementException:
        print("      [!] No se encontraron filas de cuatrimestres.")

def guardar_en_csv_final(ruta_csv, datos, encabezados):
    """
    Guarda los datos en un archivo CSV en modo append.
    :param ruta_csv: Ruta al archivo CSV.
    :param datos: Lista de diccionarios con los datos.
    :param encabezados: Lista de encabezados para el CSV.
    """
    file_exists = os.path.isfile(ruta_csv)
    with open(ruta_csv, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=encabezados)
        if not file_exists:
            writer.writeheader()
        for dato in datos:
            writer.writerow(dato)
    print(f"          [>] Se ha guardado un registro en '{os.path.abspath(ruta_csv)}'.")

# --- Script Principal ---

def main():
    global total_sleep_time
    start_time = time.time()
    # Configurar el WebDriver
    driver = configurar_driver()

    try:
        # Navegar a la página de "Materias"
        driver.get(MATERIAS_URL)
        print(f"Accedido a la página de Materias: {MATERIAS_URL}")

        # Manejar la paginación y extraer las materias
        manejar_paginacion_materias(driver)

    finally:
        # Cerrar el WebDriver
        driver.quit()
        # Mostrar tiempo total de espera
        horas, rem = divmod(total_sleep_time, 3600)
        minutos, segundos = divmod(rem, 60)
        print(f"\nTiempo total de pausas (sleep): {int(horas)}h {int(minutos)}m {int(segundos)}s.")

if __name__ == "__main__":
    main()
