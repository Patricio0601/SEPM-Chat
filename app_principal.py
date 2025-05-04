from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime
import json
import logging
from PIL import Image  # Adicionado para OCR
import pytesseract  # Adicionado para OCR
from unidecode import unidecode

app = Flask(__name__)

# Configuração de logging
logging.basicConfig(filename='sepm_chat.log', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Caminho para o histórico, licitações e almoxarifado
HISTORY_FILE = 'app_DF/consultas.json'
LICITACOES_FILE = 'licitacoes.json'
ALMOXARIFADO_FILE = 'almoxarifado.json'

# Carregar histórico ao iniciar
def carregar_historico():
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        logging.error(f"Erro ao carregar histórico: {e}")
        return []

# Carregar licitações ao iniciar
licitacoes_data = []
def carregar_licitacoes():
    global licitacoes_data
    try:
        with open(LICITACOES_FILE, 'r', encoding='utf-8') as f:
            licitacoes_data = json.load(f)
        logging.info("Licitações carregadas com sucesso.")
    except FileNotFoundError:
        logging.error("Arquivo licitacoes.json não encontrado.")
        licitacoes_data = []
    except Exception as e:
        logging.error(f"Erro ao carregar licitações: {e}")
        licitacoes_data = []

# Carregar itens do almoxarifado
itens_almoxarifado = []
def carregar_almoxarifado():
    global itens_almoxarifado
    try:
        with open(ALMOXARIFADO_FILE, 'r', encoding='utf-8') as f:
            itens_almoxarifado = json.load(f).get("itens_almoxarifado", [])
        logging.info("Itens do almoxarifado carregados com sucesso.")
    except FileNotFoundError:
        logging.error("Arquivo almoxarifado.json não encontrado.")
        itens_almoxarifado = []
    except Exception as e:
        logging.error(f"Erro ao carregar almoxarifado: {e}")
        itens_almoxarifado = []

# Carregar restrições
def carregar_restricoes():
    try:
        with open('restricoes.json', 'r', encoding='utf-8') as f:
            return json.load(f).get("itens_vedados", [])
    except FileNotFoundError:
        logging.warning("restricoes.json não encontrado. Usando lista padrão.")
        return ["alimentos", "combustíveis", "bebidas alcoólicas", "material de limpeza", "itens de escritório"]

# Salvar histórico
def salvar_historico(historico):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(historico, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Erro ao salvar histórico: {e}")

# Listas de itens
ITENS_VEDADOS = carregar_restricoes()
ITENS_ALMOXARIFADO = itens_almoxarifado

# Função para extrair texto de imagens
def extrair_texto_imagem(imagem_path):
    try:
        imagem = Image.open(imagem_path)
        texto = pytesseract.image_to_string(imagem, lang='por')
        logging.info(f"Texto extraído da imagem: {texto}")
        return texto
    except Exception as e:
        logging.error(f"Erro ao extrair texto da imagem: {e}")
        return ""

# Verificar contrato em imagem
def verificar_contrato_imagem(texto, item):
    texto_normalizado = unidecode(texto.lower())
    item_normalizado = unidecode(item.lower())
    status = "não encontrado"
    detalhes = "Nenhum contrato vigente identificado na imagem."

    if item_normalizado in texto_normalizado and "adjudicado" in texto_normalizado:
        status = "encontrado"
        detalhes = "Item presente em contrato vigente identificado na imagem (status: adjudicado)."
    
    return {"status": status, "detalhes": detalhes}

# Buscar licitações no JSON
def buscar_licitacoes_json(item):
    item_normalizado = unidecode(item.lower())
    hoje = datetime.now()
    dois_anos_atras = hoje.replace(year=hoje.year - 2)  # Contratos dos últimos 2 anos são considerados vigentes

    for licitacao in licitacoes_data:
        descricao_normalizada = unidecode(licitacao['descricao'].lower())
        if item_normalizado in descricao_normalizada:
            try:
                data_realizacao = datetime.strptime(licitacao['data_realizacao'], '%d/%m/%Y')
                if data_realizacao >= dois_anos_atras:
                    return {
                        "status": "encontrado",
                        "detalhes": f"Licitação em andamento: {licitacao['descricao']} (Protocolo: {licitacao['protocolo_processo']}, Data: {licitacao['data_realizacao']})"
                    }
            except ValueError as e:
                logging.error(f"Erro ao parsear data da licitação {licitacao['protocolo_processo']}: {e}")
                continue
    
    return {"status": "não encontrado", "detalhes": "Nenhuma licitação em andamento encontrada."}

# Função principal do chatbot
def consultar_ollama(unidade, posto_graduacao, nome, rg, item, valor_total, mensagem, imagem_path=None):
    item_normalizado = unidecode(item.lower())
    valor_total = float(valor_total.replace("R$", "").replace(".", "").replace(",", ".").strip())
    chat_response = f"Usuário: {posto_graduacao} {nome} (RG: {rg}) - Unidade: {unidade}\n"
    chat_response += f"Item consultado: {item} | Valor total: R$ {valor_total:,.2f}\n"

    # Verificar se há imagem e processar OCR
    contrato_imagem = {"status": "não encontrado", "detalhes": "Nenhuma imagem fornecida."}
    if imagem_path:
        texto_imagem = extrair_texto_imagem(imagem_path)
        contrato_imagem = verificar_contrato_imagem(texto_imagem, item)
        chat_response += f"Resultado da análise da imagem: {contrato_imagem['detalhes']}\n"

    # Verificar restrições internas
    if any(item_vedado in item_normalizado for item_vedado in ITENS_VEDADOS):
        chat_response += "Status: Item vedado para aquisição via Suprimento de Fundos.\n"
        chat_response += "Aconselhamento: Este item não pode ser adquirido devido a restrições internas.\n"
        return chat_response

    # Verificar disponibilidade no almoxarifado
    if any(almox_item in item_normalizado for almox_item in ITENS_ALMOXARIFADO):
        chat_response += "Status: Item disponível no almoxarifado virtual.\n"
        chat_response += "Aconselhamento: Solicite o item diretamente ao almoxarifado da sua unidade.\n"
        return chat_response

    # Verificar licitações em andamento
    resultado_licitacao = buscar_licitacoes_json(item)
    chat_response += f"Resultado da busca de licitações: {resultado_licitacao['detalhes']}\n"

    if resultado_licitacao["status"] == "encontrado" or contrato_imagem["status"] == "encontrado":
        chat_response += "Status: Licitação em andamento identificada.\n"
        chat_response += "Aconselhamento: O item deve ser adquirido por meio da licitação vigente.\n"
        return chat_response

    # Se não há restrições, o item pode ser adquirido
    chat_response += "Status: Viável para aquisição via Suprimento de Fundos.\n"
    chat_response += "Aconselhamento: O item pode ser adquirido via Suprimento de Fundos, desde que respeitadas as normativas internas.\n"
    return chat_response

# Salvar no histórico
def salvar_no_historico(unidade, posto_graduacao, nome, rg, item, valor_total, mensagem, resposta):
    historico = carregar_historico()
    nova_entrada = {
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "unidade": unidade,
        "posto_graduacao": posto_graduacao,
        "nome": nome,
        "rg": rg,
        "item": item,
        "valor_total": valor_total,
        "mensagem": mensagem,
        "resposta": resposta
    }
    historico.append(nova_entrada)
    salvar_historico(historico)

# Gerar relatório diário
def gerar_relatorio_diario():
    historico = carregar_historico()
    hoje = datetime.now().strftime("%Y-%m-%d")
    relatorio = [entry for entry in historico if entry["data"].startswith(hoje)]
    return relatorio

# Rotas
@app.route('/')
def index():
    historico = carregar_historico()
    return render_template('index.html', historico=historico)

@app.route('/chat', methods=['POST'])
def chat():
    unidade = request.form['unidade']
    posto_graduacao = request.form['posto_graduacao']
    nome = request.form['nome']
    rg = request.form['rg']
    item = request.form['item']
    valor_total = request.form['valor_total']
    mensagem = request.form['mensagem']
    imagem = request.files.get('imagem')

    imagem_path = None
    if imagem:
        imagem_path = f"app_DF/{imagem.filename}"
        imagem.save(imagem_path)

    try:
        resposta = consultar_ollama(unidade, posto_graduacao, nome, rg, item, valor_total, mensagem, imagem_path)
        salvar_no_historico(unidade, posto_graduacao, nome, rg, item, valor_total, mensagem, resposta)
    except Exception as e:
        logging.error(f"Erro ao processar consulta: {e}")
        resposta = "Erro ao processar a consulta. Por favor, tente novamente."

    return redirect(url_for('index'))

@app.route('/relatorio', methods=['GET'])
def relatorio():
    return jsonify(gerar_relatorio_diario())

# Carregar dados ao iniciar o app
carregar_licitacoes()
carregar_almoxarifado()

if __name__ == '__main__':
    app.run(debug=True)