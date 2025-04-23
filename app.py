from flask import Flask, render_template, request, jsonify, redirect, url_for
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import json
import os
import logging
import time
import subprocess
from PIL import Image  # Adicionado para OCR
import pytesseract     # Adicionado para OCR
from unidecode import unidecode
from threading import Lock  # Adicionado para sincronização
from threading import Lock  # Adicionado para sincronização

app = Flask(__name__)

# Configurar logging
logging.basicConfig(filename='sepm_chat.log', level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Caminho para o arquivo JSON de histórico
HISTORY_FILE = os.path.join("app_DF", "consultas.json")

# Lock para evitar execuções simultâneas do scraper
scraper_lock = Lock()

# Função para extrair texto da imagem
def extrair_texto_imagem(caminho_imagem):
    try:
        # Carregar a imagem
        imagem = Image.open(caminho_imagem)
        
        # Extrair texto da imagem com pytesseract
        texto = pytesseract.image_to_string(imagem, lang='por')  # 'por' para português
        logging.debug(f"Texto extraído da imagem: {texto[:500]}")  # Logar os primeiros 500 caracteres para depuração
        
        return texto
    except Exception as e:
        logging.error(f"Erro ao extrair texto da imagem: {str(e)}")
        return ""

# Função para verificar contratos na imagem
def verificar_contrato_imagem(texto_imagem, item):
    if not texto_imagem:
        return {"status": "não encontrado", "detalhes": "Nenhuma informação extraída da imagem."}
    
    # Normalizar o item e o texto da imagem
    item_normalized = unidecode(item.lower())
    texto_normalized = unidecode(texto_imagem.lower())
    
    # Verificar se o item está presente no texto
    item_words = item_normalized.split()
    item_found = all(word in texto_normalized for word in item_words)
    
    if not item_found:
        # Tentar uma correspondência parcial (ex.: "elétrica ppm")
        core_item = " ".join(item_words[:2])
        item_found = core_item in texto_normalized
    
    if not item_found:
        return {"status": "não encontrado", "detalhes": f"Item '{item}' não encontrado na imagem."}
    
    # Verificar se há um contrato vigente (status "ADJUDICADO")
    if "adjudicado" in texto_normalized:
        # Extrair informações do contrato (ex.: identificador e data)
        identificador_match = re.search(r'cc \d{3}/\d{2}', texto_normalized, re.IGNORECASE)
        data_match = re.search(r'\d{2}/\d{2}/\d{4}', texto_normalized)
        
        identificador = identificador_match.group(0) if identificador_match else "N/A"
        data = data_match.group(0) if data_match else "N/A"
        
        # Verificar vigência (assumindo que contratos de 2023 estão vigentes em 2025, a menos que anulados)
        if "anulado" not in texto_normalized:
            return {
                "status": "encontrado",
                "detalhes": f"Contrato vigente encontrado na imagem: {identificador}, adjudicado em {data}."
            }
    
    return {"status": "não encontrado", "detalhes": f"Item '{item}' encontrado na imagem, mas sem contrato vigente (status não é 'ADJUDICADO')."}

# Carregar histórico do arquivo JSON
def carregar_historico():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except Exception as e:
        logging.error(f"Erro ao carregar {HISTORY_FILE}: {str(e)}")
        return []

# Salvar histórico no arquivo JSON
def salvar_historico(chat_history):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(chat_history, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Erro ao salvar {HISTORY_FILE}: {str(e)}")

# Função para limpar arquivos antigos
def cleanup_old_files(age_hours=24):
    now = time.time()
    # Caminho relativo
    directory = os.path.join(os.getcwd(), "app_DF")  # Usa o diretório atual de execução

    # Verifique se o diretório existe
    if not os.path.isdir(directory):
        print(f"O diretório {directory} não existe!")
        return  # Sai da função se o diretório não existir

    for filename in os.listdir(directory):
        if filename.startswith("licitacoes_") and filename.endswith(".json"):
            filepath = os.path.join(directory, filename)
            file_age = now - os.path.getmtime(filepath)
            if file_age > age_hours * 3600:
                os.remove(filepath)
                logging.debug(f"Arquivo antigo removido: {filepath}")

# In-memory chat history inicializado com dados do JSON
chat_history = carregar_historico()

# Carregar restrições internas do arquivo JSON
def carregar_restricoes():
    caminho_restricoes = os.path.join("app_DF", "legislation", "restricoes.json")
    try:
        if os.path.exists(caminho_restricoes):
            with open(caminho_restricoes, "r", encoding="utf-8") as f:
                dados = json.load(f)
                return dados.get("itens_vedados", [])
        else:
            return [
                "gêneros alimentícios", "alimentos", "azeite", "azeite de oliva", "café", "açúcar", "arroz", "feijão",
                "combustíveis", "gasolina", "diesel",
                "peças veiculares", "pneus", "baterias",
                "serviços de limpeza", "limpeza terceirizada",
                "cerveja", "bebidas alcoólicas"
            ]
    except Exception as e:
        logging.error(f"Erro ao carregar restricoes.json: {str(e)}")
        return [
            "gêneros alimentícios", "alimentos", "azeite", "azeite de oliva", "café", "açúcar", "arroz", "feijão",
            "combustíveis", "gasolina", "diesel",
            "peças veiculares", "pneus", "baterias",
            "serviços de limpeza", "limpeza terceirizada",
            "cerveja", "bebidas alcoólicas"
        ]

ITENS_VEDADOS = carregar_restricoes()

# Função para buscar legislações online
def buscar_legislacao(termo):
    try:
        urls = [
            f"https://www.google.com/search?q={termo}+site:planalto.gov.br+site:sepm.rj.gov.br+site:portaldecompras.rj.gov.br+site:comprasnet.gov.br+site:funespol.rj.gov.br",
            "https://www.compras.rj.gov.br/contratos/listar.action?search=FUNESPOM+-+FUNDO+ESP.+POL%C3%8DCIA+MILITAR+RJ",
            "https://www.compras.rj.gov.br/portalsiga/busca?search=FUNESPOM+-+FUNDO+ESP.+POL%C3%8DCIA+MILITAR+RJ"
        ]
        headers = {'User-Agent': 'Mozilla/5.0'}
        resultados = []
        
        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=5)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    if any(site in href for site in ['planalto.gov.br', 'sepm.rj.gov.br', 'portaldecompras.rj.gov.br', 'comprasnet.gov.br', 'funespol.rj.gov.br', 'compras.rj.gov.br']):
                        if not any(rejected in href for rejected in ['Request+Rejected', 'support+ID']):
                            resultados.append({"url": href, "titulo": link.text[:100]})
            except requests.exceptions.RequestException as e:
                resultados.append({"url": "", "titulo": f"Erro ao acessar {url}: {str(e)}"})
        
        return resultados[:3] if resultados else [{"url": "", "titulo": "Nenhum resultado encontrado."}]
    except Exception as e:
        logging.error(f"Erro geral em buscar_legislacao: {str(e)}")
        return [{"url": "", "titulo": f"Erro geral: {str(e)}"}]

# Função para executar o scraper com o item
def executar_scraper(item):
    try:
        with scraper_lock:
            scraper_path = os.path.join("app_DF", "scraper.py")
            python_path = r"C:/Users/patri/AppData/Local/Programs/Python/Python313/python.exe"
            timestamp = str(int(time.time()))
            output_file = f"licitacoes_{timestamp}.json"
            env = os.environ.copy()
            env["OUTPUT_FILE"] = output_file
            result = subprocess.run([python_path, scraper_path, item], capture_output=True, text=True, timeout=300, env=env)
            logging.debug(f"Scraper executado para o item '{item}'. Saída: {result.stdout}")
            if result.stderr:
                logging.error(f"Erro ao executar o scraper: {result.stderr}")
                return None
            return output_file
    except subprocess.TimeoutExpired:
        logging.error(f"Timeout ao executar o scraper para o item '{item}'.")
        return None
    except Exception as e:
        logging.error(f"Erro ao executar o scraper para o item '{item}': {str(e)}")
        return None

# Função para ler licitações do arquivo JSON
def buscar_licitacoes(item):
    try:
        output_file = executar_scraper(item)
        if not output_file:
            return {"status": "não encontrado", "detalhes": "Erro ao executar o scraper. Verifique o log para mais detalhes."}
        
        caminho_licitacoes = os.path.join("app_DF", output_file)
        if os.path.exists(caminho_licitacoes):
            with open(caminho_licitacoes, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if dados.get("item", "").lower() == item.lower():
                    return dados.get("licitacao", {"status": "não encontrado", "detalhes": "N/A"})
                else:
                    return {"status": "não encontrado", "detalhes": f"Item no JSON não corresponde ao pesquisado: '{item}' (JSON: {dados.get('item', 'N/A')})."}
        return {"status": "não encontrado", "detalhes": "Arquivo de licitações não encontrado."}
    except json.JSONDecodeError:
        logging.error(f"Erro: {output_file} contém JSON inválido.")
        return {"status": "não encontrado", "detalhes": f"Erro ao ler {output_file}: arquivo contém JSON inválido."}
    except Exception as e:
        logging.error(f"Erro ao ler {output_file}: {str(e)}")
        return {"status": "não encontrado", "detalhes": f"Erro ao ler {output_file}: {str(e)}"}

# Função para consultar Ollama (ajustada para usar OCR)
def consultar_ollama(mensagem, historico, licitacao, item, valor_total, identificacao, caminho_imagem=None):
    almoxarifado_itens = [
        'abracadeira lacre seguranca', 'acetato transparente', 'alfinete mapa', 'almofada carimbo',
        'almofada carimbo auto-entintado', 'apagador', 'baliza topografia', 'base carimbo', 'borracha',
        'borracha escolar', 'caneta', 'caneta base fixa', 'caneta borracha', 'caneta corretiva',
        'caneta hidrografica', 'caneta laser', 'caneta marca texto', 'caneta permanente',
        'caneta personalizada (brinde)', 'caneta retroprojetor', 'caneta tecido', 'carga caneta',
        'cinta elastica para acondicionamento de processos', 'clips prendedor papel',
        'clips retratil / roller clip / prendedor cracha retratil', 'cola bastao',
        'cola liquida colorida escolar', 'cola liquida pva', 'colchete pasta', 'compasso tecnico escolar',
        'conjunto caneta hidrografica', 'corretivo liquido', 'corretivo fita', 'diluente corretivo',
        'elastico escritorio', 'escalimetro', 'etiqueta para etiquetadora', 'fita adesiva',
        'fita adesiva acetato', 'fita adesiva emenda filme', 'fita adesiva espuma', 'fita adesiva pvc',
        'fita adesiva papel crepado (crepe)', 'fita corrigivel datilografia', 'fita magica',
        'fita maquina', 'fita maquina escrever', 'fita relogio ponto', 'fita rotulador', 'giz cera',
        'giz escolar', 'giz liquido', 'grampo grampeador', 'grampo maquina reprografia, escritorio',
        'grampo pasta', 'grafite (mina lapiseira)', 'guia assinatura braille',
        'kit escrita quadro magnetico', 'lamina estilete', 'lapis', 'lapis borracha', 'lapis cor',
        'lapis pastel', 'lapis preto', 'limpador para quadro branco', 'marcador para quadro branco, jogo',
        'marcador quadro branco', 'moldura para quadro', 'moldura tela projecao', 'papel', 'percevejo',
        'perfil encadernacao', 'pincel atomico', 'pincel atomico, jogo',
        'pino plastico fixacao etiqueta (fast pin)', 'porta etiqueta magnetica',
        'pasta canaleta, escritorio', 'pasta congresso, escritorio', 'pasta envelope, escritorio',
        'pasta mochila, propaganda', 'pasta prancheta, escritorio', 'pasta promocional',
        'pasta rotoclip, escritorio', 'prendedor papel', 'purpurina/glitter', 'refil apagador quadro branco',
        'refil caneta borracha', 'refil pistola aplicadora cola quente', 'regua didatica',
        'regua plana, escala', 'resma de papel', 'saco plastico pasta (desativado)',
        'saco plastico pasta (padrao)', 'tala para arquivo medico', 'tinta carimbo',
        'tinta duplicador digital', 'tinta marcador quadro branco', 'tinta mimeografo', 'tinta nanquim',
        'tinta numerador autenticador/datador', 'tinta pincel atomico', 'toner',
        'toner para aparelho de fax', 'transparencia', 'tubo acondicionamento projetos - mapas - plantas',
        'umedecedor dedos', 'visor pasta suspensa'
    ]
    
    # Executar OCR se uma imagem foi fornecida
    resultado_imagem = {"status": "não encontrado", "detalhes": "Nenhuma imagem fornecida."}
    if caminho_imagem and os.path.exists(caminho_imagem):
        texto_imagem = extrair_texto_imagem(caminho_imagem)
        resultado_imagem = verificar_contrato_imagem(texto_imagem, item)
    
    # Verificações padrão
    no_almoxarifado = item.lower() in almoxarifado_itens if item else False
    materiais_construcao = ['tijolo', 'tijolos', 'cimento', 'areia', 'terra', 'tinta']
    eh_material_construcao = any(m.lower() in item.lower() for m in materiais_construcao) if item else False
    eh_vedado = any(vedado in item.lower() for vedado in ITENS_VEDADOS) if item else False
    try:
        valor = float(valor_total.replace('R$', '').replace(',', '.').strip())
    except (ValueError, AttributeError):
        valor = 0.0
        logging.error(f"Erro ao converter valor_total '{valor_total}' para float.")
    limite_compras_servicos = 62725.59
    limite_obras = 125451.15
    limite_aplicavel = limite_obras if eh_material_construcao else limite_compras_servicos
    dentro_do_limite = valor <= limite_aplicavel
    
    # Validação da identificação
    if identificacao not in mensagem:
        logging.warning(f"Discrepância na identificação: mensagem='{mensagem}', identificacao='{identificacao}'")
    
    # Priorizar a imagem se houver contrato vigente
    if resultado_imagem["status"] == "encontrado":
        return (
            f"Identificação do Usuário: {identificacao}\n\n"
            f"Resposta Objetiva: Não é permitido adquirir '{item}' (R${valor:.2f}) com Suprimento de Fundos, "
            f"pois há um contrato vigente identificado na imagem.\n\n"
            f"Status da Licitação/Contrato: {resultado_imagem['status']} ({resultado_imagem['detalhes']}).\n\n"
            f"Restrições Internas: '{item}' {'é vedado por normas internas' if eh_vedado else 'não é vedado por normas internas'}.\n\n"
            f"Fundamentação Jurídica: Lei 14.133/2021, Art. 75, inciso I.\n\n"
            f"Aconselhamento: Utilize o contrato vigente identificado na imagem ({resultado_imagem['detalhes']})."
        )
    
    # Caso contrário, seguir a lógica padrão com base no licitacoes.json
    if eh_vedado:
        return (
            f"Identificação do Usuário: {identificacao}\n\n"
            f"Resposta Objetiva: Não é permitido adquirir '{item}' (R${valor:.2f}) com Suprimento de Fundos, "
            f"pois está na lista de itens vedados pelas normas internas da SEPM/FUNESPOM.\n\n"
            f"Status da Licitação/Contrato: {licitacao['status']} ({licitacao['detalhes']}).\n\n"
            f"Restrições Internas: '{item}' é vedado pelas normas internas (ex.: {', '.join(ITENS_VEDADOS)}).\n\n"
            f"Fundamentação Jurídica: Lei 14.133/2021, Art. 75, inciso I; normas internas da SEPM/FUNESPOM.\n\n"
            f"Aconselhamento: Requisite via contrato/licitação ou consulte o almoxarifado virtual."
        )
    elif no_almoxarifado:
        return (
            f"Identificação do Usuário: {identificacao}\n\n"
            f"Resposta Objetiva: Não é permitido adquirir '{item}' (R${valor:.2f}) com Suprimento de Fundos, "
            f"pois está disponível no almoxarifado virtual.\n\n"
            f"Status da Licitação/Contrato: {licitacao['status']} ({licitacao['detalhes']}).\n\n"
            f"Restrições Internas: '{item}' não é vedado pelas normas internas.\n\n"
            f"Fundamentação Jurídica: Lei 14.133/2021, Art. 75, inciso I.\n\n"
            f"Aconselhamento: Solicite '{item}' diretamente do almoxarifado virtual."
        )
    elif eh_material_construcao:
        if dentro_do_limite and licitacao['status'] == "não encontrado":
            return (
                f"Identificação do Usuário: {identificacao}\n\n"
                f"Resposta Objetiva: É permitido adquirir '{item}' (R${valor:.2f}) com Suprimento de Fundos, "
                f"desde que haja justificativa de urgência e ausência de licitação/contrato.\n\n"
                f"Status da Licitação/Contrato: {licitacao['status']} ({licitacao['detalhes']}).\n\n"
                f"Restrições Internas: '{item}' é um material de construção e exige justificativa de urgência.\n\n"
                f"Fundamentação Jurídica: Lei 14.133/2021, Art. 75, inciso II; Decreto 12.343/2024.\n\n"
                f"Aconselhamento: Documente a urgência, verifique o almoxarifado virtual, e obtenha aprovação."
            )
        else:
            return (
                f"Identificação do Usuário: {identificacao}\n\n"
                f"Resposta Objetiva: Não é permitido adquirir '{item}' (R${valor:.2f}) com Suprimento de Fundos.\n\n"
                f"Status da Licitação/Contrato: {licitacao['status']} ({licitacao['detalhes']}).\n\n"
                f"Restrições Internas: '{item}' é um material de construção e exige justificativa de urgência.\n\n"
                f"Fundamentação Jurídica: Lei 14.133/2021, Art. 75, inciso II; Decreto 12.343/2024.\n\n"
                f"Aconselhamento: Verifique o Portal SIGA e o almoxarifado virtual. Documente a urgência, se aplicável."
            )
    else:
        if licitacao['status'] == "encontrado":
            return (
                f"Identificação do Usuário: {identificacao}\n\n"
                f"Resposta Objetiva: Não é permitido adquirir '{item}' (R${valor:.2f}) com Suprimento de Fundos, "
                f"pois há licitação/contrato vigente.\n\n"
                f"Status da Licitação/Contrato: {licitacao['status']} ({licitacao['detalhes']}).\n\n"
                f"Restrições Internas: '{item}' não é vedado pelas normas internas.\n\n"
                f"Fundamentação Jurídica: Lei 14.133/2021, Art. 75, inciso I.\n\n"
                f"Aconselhamento: Utilize o contrato/licitação vigente no Portal SIGA."
            )
        elif not dentro_do_limite:
            return (
                f"Identificação do Usuário: {identificacao}\n\n"
                f"Resposta Objetiva: Não é permitido adquirir '{item}' (R${valor:.2f}) com Suprimento de Fundos, "
                f"pois o valor ultrapassa o limite legal.\n\n"
                f"Status da Licitação/Contrato: {licitacao['status']} ({licitacao['detalhes']}).\n\n"
                f"Restrições Internas: '{item}' não é vedado pelas normas internas.\n\n"
                f"Fundamentação Jurídica: Lei 14.133/2021, Art. 75, inciso I.\n\n"
                f"Aconselhamento: Inicie uma licitação ou ajuste o valor da compra."
            )
        else:
            return (
                f"Identificação do Usuário: {identificacao}\n\n"
                f"Resposta Objetiva: É permitido adquirir '{item}' (R${valor:.2f}) com Suprimento de Fundos, "
                f"desde que não haja licitação/contrato vigente.\n\n"
                f"Status da Licitação/Contrato: {licitacao['status']} ({licitacao['detalhes']}).\n\n"
                f"Restrições Internas: '{item}' não é vedado pelas normas internas.\n\n"
                f"Fundamentação Jurídica: Lei 14.133/2021, Art. 75, inciso I.\n\n"
                f"Aconselhamento: Verifique o almoxarifado virtual e obtenha aprovação."
            )

# Função para salvar no histórico em memória e JSON
def salvar_no_historico(mensagem, resposta):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    chat_history.append({'role': 'Usuário', 'content': mensagem, 'timestamp': timestamp})
    chat_history.append({'role': 'Bot', 'content': resposta, 'timestamp': timestamp})
    salvar_historico(chat_history)

# Função para gerar relatório diário
def gerar_relatorio_diario():
    hoje = datetime.now().strftime('%Y-%m-%d')
    interacoes_hoje = [r for r in chat_history if r['timestamp'].startswith(hoje)]
    relatorio = f"Relatório Diário - {hoje}\nTotal de Interações: {len(interacoes_hoje)//2}\n"
    for i in range(0, len(interacoes_hoje), 2):
        user_msg = interacoes_hoje[i]
        bot_msg = interacoes_hoje[i+1] if i+1 < len(interacoes_hoje) else {'content': 'N/A', 'timestamp': 'N/A'}
        relatorio += f"[{user_msg['timestamp']}] Usuário: {user_msg['content']}\nBot: {bot_msg['content']}\n\n"
    return relatorio

# Executar a limpeza de arquivos antigos ao iniciar o aplicativo
cleanup_old_files(age_hours=24)

@app.route('/')
def index():
    return render_template('index.html', chat_history=chat_history)

@app.route('/chat', methods=['POST'])
def chat():
    unidade = request.form['unidade']
    posto_graduacao = request.form['posto_graduacao']
    nome = request.form['nome']
    rg = request.form['rg']
    item = request.form['item']
    valor_total = request.form['valor_total']
    mensagem = request.form['mensagem']
    identificacao = f"{unidade} - {posto_graduacao} {nome} RG {rg}"
    logging.debug(f"Identificação do usuário: {identificacao}")
    mensagem_completa = f"{identificacao}: {mensagem}"
    
    # Processar a imagem enviada pelo formulário
    caminho_imagem = None
    if 'imagem' in request.files:
        imagem = request.files['imagem']
        if imagem and imagem.filename != '':
            # Salvar a imagem temporariamente
            caminho_imagem = os.path.join("app_DF", "temp_imagem.png")
            imagem.save(caminho_imagem)
            logging.debug(f"Imagem salva em: {caminho_imagem}")
    
    legislacoes = buscar_legislacao(item) if item else []
    licitacao = buscar_licitacoes(item) if item else {"status": "não buscado", "detalhes": "N/A"}
    # Limitar o histórico enviado ao Ollama (últimas 1000 entradas)
    limited_history = chat_history[-1000:]
    historico = "\n".join([f"Usuário: {r['content']}\nBot: {limited_history[i+1]['content']}" 
                          for i, r in enumerate(limited_history) if r['role'] == 'Usuário' and i+1 < len(limited_history)])
    resposta = consultar_ollama(mensagem, historico, licitacao, item, valor_total, identificacao, caminho_imagem)
    
    # Remover a imagem temporária após o processamento
    if caminho_imagem and os.path.exists(caminho_imagem):
        os.remove(caminho_imagem)
        logging.debug(f"Imagem temporária removida: {caminho_imagem}")
    
    salvar_no_historico(mensagem_completa, resposta)
    return redirect(url_for('index'))

@app.route('/relatorio', methods=['GET'])
def relatorio():
    relatorio = gerar_relatorio_diario()
    return jsonify({'relatorio': relatorio})
from waitress import serve

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8000)
