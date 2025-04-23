from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import json
import logging
import sys
import re
import os

# Configurar logging
logging.basicConfig(filename='sepm_scraper.log', level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Receber o item como argumento de linha de comando
if len(sys.argv) < 2:
    logging.error("Nenhum item fornecido. Forneça o item como argumento (ex.: python scraper.py tijolos).")
    sys.exit(1)

item = sys.argv[1]
logging.debug(f"Item recebido para busca: {item}")

# Determinar o nome do arquivo de saída
output_file = os.getenv("OUTPUT_FILE", "licitacoes.json")
caminho_licitacoes = os.path.join("app_DF", output_file)

# Configurar o navegador
chrome_options = Options()
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.7049.96 Safari/537.36")
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

try:
    # Passo 1: Abrir a página inicial
    for attempt in range(3):
        try:
            driver.get("https://www.compras.rj.gov.br/")
            WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            logging.debug(f"Página inicial carregada. URL: {driver.current_url}")
            break
        except Exception as e:
            if attempt == 2:
                logging.error(f"Erro ao acessar o site compras.rj.gov.br após 3 tentativas: {str(e)}")
                result = {"status": "não encontrado", "detalhes": f"Erro ao acessar o site compras.rj.gov.br: {str(e)}"}
                with open(caminho_licitacoes, "w", encoding="utf-8") as f:
                    json.dump({"item": item, "licitacao": result}, f, ensure_ascii=False, indent=4)
                driver.quit()
                sys.exit()

    # Passo 2: Selecionar "Compras Públicas"
    try:
        compras_publicas = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Compras Públicas')]"))
        )
        compras_publicas.click()
        logging.debug("Link 'Compras Públicas' clicado.")
    except TimeoutException:
        logging.error("Link 'Compras Públicas' não encontrado.")
        result = {"status": "não encontrado", "detalhes": "Link 'Compras Públicas' não encontrado."}
        with open(caminho_licitacoes, "w", encoding="utf-8") as f:
            json.dump({"item": item, "licitacao": result}, f, ensure_ascii=False, indent=4)
        driver.quit()
        sys.exit()

    # Passo 3: Selecionar "Licitações e Processos Eletrônicos de Dispensa"
    try:
        licitacoes = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Licitações e Processos Eletrônicos de Dispensa')]"))
        )
        licitacoes.click()
        logging.debug("Link 'Licitações e Processos Eletrônicos de Dispensa' clicado.")
    except TimeoutException:
        logging.error("Link 'Licitações e Processos Eletrônicos de Dispensa' não encontrado.")
        result = {"status": "não encontrado", "detalhes": "Link 'Licitações e Processos Eletrônicos de Dispensa' não encontrado."}
        with open(caminho_licitacoes, "w", encoding="utf-8") as f:
            json.dump({"item": item, "licitacao": result}, f, ensure_ascii=False, indent=4)
        driver.quit()
        sys.exit()

    # Passo 4: Esperar a página carregar completamente
    try:
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.XPATH, "//label[contains(text(), 'Unidade')]"))
        )
        time.sleep(5)
        logging.debug("Página de pesquisa carregada.")
    except TimeoutException:
        logging.error("Página de pesquisa não carregou completamente (label 'Unidade' não encontrado).")
        result = {"status": "não encontrado", "detalhes": "Página de pesquisa não carregou completamente (label 'Unidade' não encontrado)."}
        with open(caminho_licitacoes, "w", encoding="utf-8") as f:
            json.dump({"item": item, "licitacao": result}, f, ensure_ascii=False, indent=4)
        driver.quit()
        sys.exit()

    # Passo 5: Rolar até o campo "Unidade"
    try:
        unidade_label = driver.find_element(By.XPATH, "//label[contains(text(), 'Unidade')]")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", unidade_label)
        time.sleep(2)
        logging.debug("Rolado até o campo 'Unidade'.")
    except Exception as e:
        logging.error(f"Erro ao rolar até o campo 'Unidade': {str(e)}")
        result = {"status": "não encontrado", "detalhes": f"Erro ao rolar até o campo 'Unidade': {str(e)}"}
        with open(caminho_licitacoes, "w", encoding="utf-8") as f:
            json.dump({"item": item, "licitacao": result}, f, ensure_ascii=False, indent=4)
        driver.quit()
        sys.exit()

    # Passo 6: Selecionar "FUNESPOM"
    try:
        unidade_select = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, "//label[contains(text(), 'Unidade')]/following-sibling::select | //label[contains(text(), 'Unidade')]/following-sibling::div//select"))
        )
        select = Select(unidade_select)
        select.select_by_visible_text("FUNESPOM")
        logging.debug("Opção 'FUNESPOM' selecionada com Select.")
        time.sleep(5)
    except TimeoutException:
        logging.error("Dropdown 'Unidade' ou opção 'FUNESPOM' não encontrada.")
        result = {"status": "não encontrado", "detalhes": "Dropdown 'Unidade' ou opção 'FUNESPOM' não encontrada."}
        with open(caminho_licitacoes, "w", encoding="utf-8") as f:
            json.dump({"item": item, "licitacao": result}, f, ensure_ascii=False, indent=4)
        driver.quit()
        sys.exit()

    # Passo 7: Aguardar a página carregar os resultados
    try:
        WebDriverWait(driver, 90).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(10)
        logging.debug("Página de resultados carregada com sucesso.")
    except TimeoutException:
        logging.error("Página de resultados não carregada após selecionar 'FUNESPOM'.")
        result = {"status": "não encontrado", "detalhes": "Página de resultados não carregada após selecionar 'FUNESPOM'."}
        with open(caminho_licitacoes, "w", encoding="utf-8") as f:
            json.dump({"item": item, "licitacao": result}, f, ensure_ascii=False, indent=4)
        driver.quit()
        sys.exit()

    # Passo 8: Buscar o item em qualquer lugar da página
    try:
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.XPATH, "//table | //div[contains(@class, 'result')] | //ul"))
        )
        time.sleep(5)

        item_found = False
        context = ""
        max_pages = 5

        while True:
            body = driver.find_element(By.TAG_NAME, "body")
            page_text = body.text.strip().lower()
            logging.debug(f"Texto extraído da página: {page_text[:1000]}")

            item_cleaned = re.sub(r'[^a-z0-9\s]', '', item.lower()).strip()
            item_cleaned = re.sub(r'\s+', ' ', item_cleaned)
            logging.debug(f"Item normalizado: {item_cleaned}")

            page_lines = [line.strip() for line in page_text.split('\n') if line.strip()]
            for line in page_lines:
                line_cleaned = re.sub(r'[^a-z0-9\s]', '', line).strip()
                line_cleaned = re.sub(r'\s+', ' ', line_cleaned)
                item_words = item_cleaned.split()
                line_words = line_cleaned.split()
                if all(word in line_words for word in item_words):
                    item_found = True
                    context = line
                    logging.debug(f"Item '{item}' encontrado na linha: {context}")
                    break

            if item_found:
                break

            try:
                next_button = driver.find_element(By.XPATH, "//a[contains(text(), 'Próxima') or contains(text(), 'Next')]")
                if not next_button.is_enabled():
                    logging.debug("Não há mais páginas para navegar.")
                    break
                next_button.click()
                time.sleep(5)
                max_pages -= 1
                if max_pages == 0:
                    logging.debug("Limite de páginas atingido.")
                    break
            except NoSuchElementException:
                logging.debug("Botão 'Próxima' não encontrado. Finalizando busca.")
                break

        if item_found:
            result = {
                "status": "encontrado",
                "detalhes": f"Item encontrado na página. Contexto: {context[:100]}"
            }
        else:
            result = {
                "status": "não encontrado",
                "detalhes": f"Item '{item}' não encontrado nas páginas pesquisadas."
            }

        with open(caminho_licitacoes, "w", encoding="utf-8") as f:
            json.dump({"item": item, "licitacao": result}, f, ensure_ascii=False, indent=4)

except Exception as e:
    logging.error(f"Erro geral no scraper: {str(e)}")
    result = {"status": "não encontrado", "detalhes": f"Erro geral no scraper: {str(e)}"}
    with open(caminho_licitacoes, "w", encoding="utf-8") as f:
        json.dump({"item": item, "licitacao": result}, f, ensure_ascii=False, indent=4)

finally:
    driver.quit()
    logging.debug("WebDriver encerrado com sucesso.")
