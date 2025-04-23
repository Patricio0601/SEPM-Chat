from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
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
# chrome_options.add_argument("--headless")  # Descomente para rodar sem interface gráfica
driver = webdriver.Chrome(options=chrome_options)

try:
    # Passo 1: Abrir a página inicial
    for attempt in range(3):
        try:
            driver.get("https://www.compras.rj.gov.br/")
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
    except TimeoutException:
        logging.error("Link 'Licitações e Processos Eletrônicos de Dispensa' não encontrado.")
        result = {"status": "não encontrado", "detalhes": "Link 'Licitações e Processos Eletrônicos de Dispensa' não encontrado."}
        with open(caminho_licitacoes, "w", encoding="utf-8") as f:
            json.dump({"item": item, "licitacao": result}, f, ensure_ascii=False, indent=4)
        driver.quit()
        sys.exit()

    # Passo 4: Esperar a página carregar completamente
    try:
        WebDriverWait(driver, 45).until(
            EC.presence_of_element_located((By.XPATH, "//label[contains(text(), 'Unidade')]"))
        )
        time.sleep(5)
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
    except Exception as e:
        logging.error(f"Erro ao rolar até o campo 'Unidade': {str(e)}")
        result = {"status": "não encontrado", "detalhes": f"Erro ao rolar até o campo 'Unidade': {str(e)}"}
        with open(caminho_licitacoes, "w", encoding="utf-8") as f:
            json.dump({"item": item, "licitacao": result}, f, ensure_ascii=False, indent=4)
        driver.quit()
        sys.exit()

    # Passo 6: Selecionar "FUNESPOM", clicar em um campo neutro e pressionar "Enter"
    try:
        unidade_select = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//label[contains(text(), 'Unidade')]/following-sibling::select | //label[contains(text(), 'Unidade')]/following-sibling::div//select"))
        )
        unidade_select.click()
        time.sleep(3)

        opcao_sepm = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//option[contains(text(), 'FUNESPOM')]"))
        )
        opcao_sepm.click()
        logging.debug("Opção 'FUNESPOM' selecionada com clique direto.")

        try:
            campo_neutro = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, "//label[contains(text(), 'Unidade')]"))
            )
            campo_neutro.click()
            logging.debug("Clicado no campo neutro (label 'Unidade').")
        except TimeoutException:
            campo_neutro = driver.find_element(By.TAG_NAME, "body")
            campo_neutro.click()
            logging.debug("Clicado no campo neutro (body da página).")

        unidade_select.send_keys(Keys.ENTER)
        logging.debug("Tecla 'Enter' pressionada no dropdown.")

    except TimeoutException:
        logging.error("Opção 'FUNESPOM' não encontrada no dropdown ou dropdown não carregado.")
        result = {"status": "não encontrado", "detalhes": "Opção 'FUNESPOM' não encontrada no dropdown ou dropdown não carregado."}
        with open(caminho_licitacoes, "w", encoding="utf-8") as f:
            json.dump({"item": item, "licitacao": result}, f, ensure_ascii=False, indent=4)
        driver.quit()
        sys.exit()

    except Exception as e:
        logging.error(f"Erro ao selecionar a unidade 'FUNESPOM', clicar no campo neutro ou pressionar 'Enter': {str(e)}")
        result = {"status": "não encontrado", "detalhes": f"Erro ao selecionar a unidade 'FUNESPOM': {str(e)}"}
        with open(caminho_licitacoes, "w", encoding="utf-8") as f:
            json.dump({"item": item, "licitacao": result}, f, ensure_ascii=False, indent=4)
        driver.quit()
        sys.exit()

    # Passo 7: Aguardar a página carregar os resultados após selecionar "FUNESPOM"
    try:
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(5)
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
        # Extrair todo o texto visível da página
        body = driver.find_element(By.TAG_NAME, "body")
        page_text = body.text.strip().lower()
        logging.debug(f"Texto extraído da página: {page_text[:1000]}")

        # Normalizar o item
        item_cleaned = re.sub(r'[^a-z0-9\s]', '', item.lower()).strip()
        item_cleaned = re.sub(r'\s+', ' ', item_cleaned)
        logging.debug(f"Item normalizado: {item_cleaned}")

        # Dividir o texto da página em linhas para uma correspondência mais precisa
        page_lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        item_found = False
        context = ""

        for line in page_lines:
            line_cleaned = re.sub(r'[^a-z0-9\s]', '', line).strip()
            line_cleaned = re.sub(r'\s+', ' ', line_cleaned)
            # Verificar se a linha contém todas as palavras do item (ignorando a ordem)
            item_words = item_cleaned.split()
            line_words = line_cleaned.split()
            if all(word in line_words for word in item_words):
                item_found = True
                context = line
                logging.debug(f"Item '{item}' encontrado na linha: {context}")
                break

        if item_found:
            result = {
                "status": "encontrado",
                "detalhes": f"Item encontrado na página. Contexto: {context[:100]}"
            }
            with open(caminho_licitacoes, "w", encoding="utf-8") as f:
                json.dump({"item": item, "licitacao": result}, f, ensure_ascii=False, indent=4)
            driver.quit()
            sys.exit()
        else:
            logging.debug(f"Item '{item}' não encontrado na página.")
            result = {
                "status": "não encontrado",
                "detalhes": f"Item '{item}' não encontrado na página."
            }
            with open(caminho_licitacoes, "w", encoding="utf-8") as f:
                json.dump({"item": item, "licitacao": result}, f, ensure_ascii=False, indent=4)

    except Exception as e:
        logging.error(f"Erro ao buscar o item na página: {str(e)}")
        result = {"status": "não encontrado", "detalhes": f"Erro ao buscar o item na página: {str(e)}"}
        with open(caminho_licitacoes, "w", encoding="utf-8") as f:
            json.dump({"item": item, "licitacao": result}, f, ensure_ascii=False, indent=4)

finally:
    driver.quit()
    logging.debug("WebDriver encerrado com sucesso.")