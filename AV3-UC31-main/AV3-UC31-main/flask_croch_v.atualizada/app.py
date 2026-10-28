"""CROCH Salgadaria — sistema de pedidos online em Flask (dados em JSON, sem banco de dados)."""

import json
import os
from datetime import datetime
from functools import wraps
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
    jsonify,
)
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS_DIR = os.path.join(BASE_DIR, "dados")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")

# Cria a pasta de uploads se não existir
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("CROCH_SECRET", "croch-salgadaria-chave-secreta")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB

# ============================================================
# CONFIGURAÇÕES DE E-MAIL
# ============================================================
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USER = "leticiagabrielly19010@gmail.com"
EMAIL_PASSWORD = "sswwafgwvypiftdw"
EMAIL_USE_TLS = True

# ============================================================
# CONFIGURAÇÕES DE PAGAMENTO
# ============================================================
PIX_CHAVE = "leticiagabrielly19010@gmail.com"
PIX_NOME = "CROCH Salgadaria"
PIX_CIDADE = "Natal"

# ---------------------------------------------------------------- persistência
def ler_json(nome):
    caminho = os.path.join(DADOS_DIR, nome)
    if not os.path.exists(caminho):
        return []
    with open(caminho, "r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


def gravar_json(nome, dados):
    caminho = os.path.join(DADOS_DIR, nome)
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)


def todos_produtos():
    """Produtos avulsos + combos, como uma lista única."""
    produtos = ler_json("produtos.json")
    combos = ler_json("combos.json")
    
    # Garante que todos os produtos tenham disponivel=True
    for p in produtos:
        if "disponivel" not in p:
            p["disponivel"] = True
    for c in combos:
        if "disponivel" not in c:
            c["disponivel"] = True
    
    return produtos + combos


def buscar_produto(produto_id):
    """Busca um produto pelo ID em produtos.json e combos.json"""
    # Procura em produtos.json
    for produto in ler_json("produtos.json"):
        if produto["id"] == produto_id:
            return produto
    # Procura em combos.json
    for combo in ler_json("combos.json"):
        if combo["id"] == produto_id:
            return combo
    return None


def salvar_produto(produto):
    """Grava no arquivo correto conforme a categoria (Combos vai para combos.json)."""
    arquivo = "combos.json" if produto.get("categoria") == "Combos" else "produtos.json"
    outro = "produtos.json" if arquivo == "combos.json" else "combos.json"

    lista_outro = [p for p in ler_json(outro) if p["id"] != produto["id"]]
    gravar_json(outro, lista_outro)

    lista = ler_json(arquivo)
    for indice, item in enumerate(lista):
        if item["id"] == produto["id"]:
            lista[indice] = produto
            break
    else:
        lista.append(produto)
    gravar_json(arquivo, lista)


def excluir_produto(produto_id):
    for arquivo in ("produtos.json", "combos.json"):
        lista = ler_json(arquivo)
        nova = [p for p in lista if p["id"] != produto_id]
        if len(nova) != len(lista):
            gravar_json(arquivo, nova)


# -------------------------------------------------------------------- sessão
def usuario_logado():
    uid = session.get("usuario_id")
    if not uid:
        return None
    for usuario in ler_json("usuarios.json"):
        if usuario["id"] == uid:
            return usuario
    return None


def somente_admin(funcao):
    @wraps(funcao)
    def interna(*args, **kwargs):
        usuario = usuario_logado()
        if not usuario or usuario.get("papel") != "admin":
            return render_template("restrito.html"), 403
        return funcao(*args, **kwargs)

    return interna


# ------------------------------------------------------------------ carrinho
def carrinho_atual():
    return session.get("carrinho", [])


def gravar_carrinho(itens):
    session["carrinho"] = itens
    session.modified = True


def total_carrinho(itens=None):
    itens = carrinho_atual() if itens is None else itens
    return round(sum(i["preco"] * i["qtd"] for i in itens), 2)


# ------------------------------------------------------------------- filtros
IMAGENS = {
    "logo": "img/logo.jpg",
    "coxinha": "img/coxinha.png",
    "caixa": "img/caixa.png",
    "refri": "img/refri.png",
    "salgados": "img/salgados.jpg",
    "molhos": "img/molhos.jpg",
    "combo-festa": "img/combo-festa.jpg",
}


@app.template_filter("moeda")
def filtro_moeda(valor):
    texto = f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


@app.template_filter("datahora")
def filtro_datahora(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return iso


@app.template_global("imagem_de")
def imagem_de(chave):
    if chave and chave.startswith("uploads/"):
        return url_for("static", filename=chave)
    return url_for("static", filename=IMAGENS.get(chave, IMAGENS["salgados"]))


@app.context_processor
def contexto_global():
    itens = carrinho_atual()
    user = usuario_logado()
    is_admin = user and user.get("papel") == "admin"
    
    notificacoes = {}
    if is_admin:
        pedidos = ler_json("pedidos.json")
        mensagens = ler_json("mensagens.json")
        comentarios = ler_json("comentarios.json")
        duvidas = ler_json("ajuda.json")
        pagamentos = ler_json("pagamentos.json")
        
        pedidos_pendentes = 0
        for pedido in pedidos:
            if pedido["status"] == "Aguardando pagamento":
                for pag in pagamentos:
                    if pag["pedido_id"] == pedido["id"] and pag["status"] != "pago":
                        pedidos_pendentes += 1
                        break
        
        notificacoes = {
            "pedidos": len([p for p in pedidos if p["status"] != "Entregue"]),
            "pagamentos_pendentes": pedidos_pendentes,
            "mensagens": len(mensagens),
            "comentarios": len([c for c in comentarios if not c.get("resposta")]),
            "ajuda": len([d for d in duvidas if not d.get("resposta")]),
        }
    
    return {
        "usuario": user,
        "carrinho": itens,
        "total_itens": sum(i["qtd"] for i in itens),
        "total_carrinho": total_carrinho(itens),
        "ano": datetime.now().year,
        "is_admin": is_admin,
        "notificacoes": notificacoes,
        "ler_json": ler_json,
        "todos_produtos": todos_produtos,
    }


# ============================================================
# SISTEMA DE PAGAMENTO
# ============================================================

def gerar_codigo_pix(pedido_id, valor, descricao):
    chave = PIX_CHAVE
    nome = PIX_NOME
    cidade = PIX_CIDADE
    
    pix = "000201"
    pix += "26440014BR.GOV.BCB.PIX"
    pix += f"01{len(chave):02d}{chave}"
    pix += "52040000"
    pix += f"53{valor:.2f}"
    pix += "58BR"
    pix += f"59{len(nome):02d}{nome}"
    pix += f"60{len(cidade):02d}{cidade}"
    
    if descricao:
        pix += f"62{len(descricao)+4:02d}05{len(descricao):02d}{descricao}"
    
    pix += "6304"
    
    crc = 0xFFFF
    for c in pix:
        crc ^= ord(c) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    
    crc_hex = f"{crc:04X}"
    return pix[:-4] + crc_hex


def gerar_pix(pedido_id, valor, descricao="Pedido CROCH Salgadaria"):
    try:
        pix_code = gerar_codigo_pix(pedido_id, valor, descricao)
        return {
            "sucesso": True,
            "pix_code": pix_code,
            "valor": valor,
            "pedido_id": pedido_id,
            "chave": PIX_CHAVE
        }
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}


def criar_pagamento_pedido(pedido_id):
    pagamentos = ler_json("pagamentos.json")
    for p in pagamentos:
        if p["pedido_id"] == pedido_id:
            return p
    
    pagamento = {
        "id": f"pag-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "pedido_id": pedido_id,
        "status": "pendente",
        "metodo": None,
        "data_criacao": datetime.now().isoformat(timespec="seconds"),
        "data_pagamento": None,
        "valor": None
    }
    pagamentos.append(pagamento)
    gravar_json("pagamentos.json", pagamentos)
    return pagamento


def atualizar_status_pagamento(pedido_id, status, metodo=None):
    pagamentos = ler_json("pagamentos.json")
    for i, p in enumerate(pagamentos):
        if p["pedido_id"] == pedido_id:
            pagamentos[i]["status"] = status
            if metodo:
                pagamentos[i]["metodo"] = metodo
            if status == "pago":
                pagamentos[i]["data_pagamento"] = datetime.now().isoformat(timespec="seconds")
            gravar_json("pagamentos.json", pagamentos)
            return True
    return False


# ============================================================
# ROTAS DE PAGAMENTO
# ============================================================

@app.route("/checkout")
def checkout():
    usuario = usuario_logado()
    if not usuario:
        flash("Faça login para finalizar o pedido.", "erro")
        return redirect(url_for("login"))
    
    if usuario.get("papel") == "admin":
        flash("Administradores não podem fazer compras.", "erro")
        return redirect(url_for("admin"))
    
    itens = carrinho_atual()
    if not itens:
        flash("Seu carrinho está vazio.", "erro")
        return redirect(url_for("carrinho_view"))
    
    total = total_carrinho(itens)
    entrega = 8.00
    
    return render_template(
        "checkout.html",
        itens=itens,
        total=total,
        entrega=entrega,
        total_final=total + entrega,
        usuario=usuario
    )


@app.route("/checkout/finalizar", methods=["POST"])
def checkout_finalizar():
    usuario = usuario_logado()
    if not usuario:
        flash("Faça login para finalizar o pedido.", "erro")
        return redirect(url_for("login"))
    
    if usuario.get("papel") == "admin":
        flash("Administradores não podem fazer compras.", "erro")
        return redirect(url_for("admin"))
    
    itens = carrinho_atual()
    if not itens:
        flash("Seu carrinho está vazio.", "erro")
        return redirect(url_for("carrinho_view"))
    
    metodo_pagamento = request.form.get("metodo_pagamento")
    if not metodo_pagamento:
        flash("Selecione um método de pagamento.", "erro")
        return redirect(url_for("checkout"))
    
    for item in itens:
        produto = buscar_produto(item["id"])
        if not produto or not produto.get("disponivel", True):
            flash(f"{item['nome']} está indisponível.", "erro")
            return redirect(url_for("carrinho_view"))
    
    pedidos = ler_json("pedidos.json")
    pedido_id = f"PD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    total = total_carrinho(itens) + 8.00
    
    pedido = {
        "id": pedido_id,
        "cliente": usuario["nome"],
        "email": usuario["email"],
        "data": datetime.now().isoformat(timespec="seconds"),
        "itens": itens.copy(),
        "total": total,
        "status": "Aguardando pagamento",
        "metodo_pagamento": metodo_pagamento
    }
    
    gravar_json("pedidos.json", [pedido] + pedidos)
    criar_pagamento_pedido(pedido_id)
    gravar_carrinho([])
    
    flash("Pedido criado! Aguarde o pagamento.", "sucesso")
    return redirect(url_for("pagamento", pedido_id=pedido_id))


@app.route("/pagamento/<pedido_id>")
def pagamento(pedido_id):
    usuario = usuario_logado()
    if not usuario:
        flash("Faça login para acessar.", "erro")
        return redirect(url_for("login"))
    
    pedido = None
    for p in ler_json("pedidos.json"):
        if p["id"] == pedido_id and p["email"] == usuario["email"]:
            pedido = p
            break
    
    if not pedido:
        flash("Pedido não encontrado.", "erro")
        return redirect(url_for("meus_pedidos"))
    
    pagamentos = ler_json("pagamentos.json")
    pagamento = None
    for p in pagamentos:
        if p["pedido_id"] == pedido_id:
            pagamento = p
            break
    
    if pagamento and pagamento["status"] == "pago":
        flash("Este pedido já foi pago.", "sucesso")
        return redirect(url_for("meus_pedidos"))
    
    pix_data = None
    if pedido["metodo_pagamento"] == "pix":
        pix_data = gerar_pix(pedido_id, pedido["total"], f"Pedido {pedido_id}")
    
    return render_template(
        "pagamento.html",
        pedido=pedido,
        pagamento=pagamento,
        pix=pix_data
    )


@app.route("/pagamento/confirmar/<pedido_id>", methods=["POST"])
def confirmar_pagamento(pedido_id):
    usuario = usuario_logado()
    if not usuario:
        flash("Faça login para confirmar.", "erro")
        return redirect(url_for("login"))
    
    pedidos = ler_json("pedidos.json")
    pedido_encontrado = None
    for i, p in enumerate(pedidos):
        if p["id"] == pedido_id and p["email"] == usuario["email"]:
            pedido_encontrado = i
            break
    
    if pedido_encontrado is None:
        flash("Pedido não encontrado.", "erro")
        return redirect(url_for("meus_pedidos"))
    
    atualizar_status_pagamento(pedido_id, "pago", "pix")
    pedidos[pedido_encontrado]["status"] = "Em preparo"
    gravar_json("pedidos.json", pedidos)
    
    flash("Pagamento confirmado! Seu pedido está sendo preparado.", "sucesso")
    return redirect(url_for("meus_pedidos"))


# ============================================================
# ADMIN - CONFIRMAR PAGAMENTO
# ============================================================

@app.route("/admin/pagamento/confirmar/<pedido_id>", methods=["POST"])
@somente_admin
def admin_confirmar_pagamento(pedido_id):
    pedidos = ler_json("pedidos.json")
    pedido_encontrado = None
    for i, p in enumerate(pedidos):
        if p["id"] == pedido_id:
            pedido_encontrado = i
            break
    
    if pedido_encontrado is None:
        flash("Pedido não encontrado.", "erro")
        return redirect(url_for("admin"))
    
    atualizar_status_pagamento(pedido_id, "pago", "admin")
    pedidos[pedido_encontrado]["status"] = "Em preparo"
    gravar_json("pedidos.json", pedidos)
    
    flash(f"✅ Pagamento do pedido {pedido_id} confirmado pelo ADMIN!", "sucesso")
    return redirect(url_for("admin"))


@app.route("/admin/pagamento/cancelar/<pedido_id>", methods=["POST"])
@somente_admin
def admin_cancelar_pagamento(pedido_id):
    pedidos = ler_json("pedidos.json")
    pedido_encontrado = None
    for i, p in enumerate(pedidos):
        if p["id"] == pedido_id:
            pedido_encontrado = i
            break
    
    if pedido_encontrado is None:
        flash("Pedido não encontrado.", "erro")
        return redirect(url_for("admin"))
    
    atualizar_status_pagamento(pedido_id, "pendente", "admin")
    pedidos[pedido_encontrado]["status"] = "Aguardando pagamento"
    gravar_json("pedidos.json", pedidos)
    
    flash(f"⚠️ Pagamento do pedido {pedido_id} cancelado.", "erro")
    return redirect(url_for("admin"))


# ======================================================================
# ROTAS PRINCIPAIS
# ======================================================================

@app.route("/")
def inicio():
    user = usuario_logado()
    if user and user.get("papel") == "admin":
        return redirect(url_for("admin"))

    produtos = todos_produtos()
    config = ler_json("config.json")
    mapa_url = config[0].get("mapa_url") if config else None

    return render_template(
        "index.html",
        destaques=[p for p in produtos if p.get("destaque")],
        combos=[p for p in produtos if p.get("categoria") == "Combos"],
        mapa_url=mapa_url,
    )


@app.route("/cardapio")
def cardapio():
    busca = (request.args.get("q") or "").strip().lower()
    categoria = request.args.get("categoria") or "Todos"
    produtos = todos_produtos()
    categorias = ["Todos"] + sorted({p["categoria"] for p in produtos})

    filtrados = [
        p
        for p in produtos
        if (categoria == "Todos" or p["categoria"] == categoria)
        and (busca in p["nome"].lower() or busca in p["descricao"].lower())
    ]
    return render_template(
        "cardapio.html",
        produtos=filtrados,
        categorias=categorias,
        categoria=categoria,
        busca=request.args.get("q") or "",
    )


@app.route("/api/produtos")
def api_produtos():
    termo = (request.args.get("q") or "").strip().lower()
    resultados = [
        {"id": p["id"], "nome": p["nome"], "categoria": p["categoria"], "preco": p["preco"]}
        for p in todos_produtos()
        if termo and termo in p["nome"].lower() and p.get("disponivel", True)
    ][:6]
    return jsonify(resultados)


@app.route("/produto/<produto_id>")
def produto(produto_id):
    item = buscar_produto(produto_id)
    if not item:
        abort(404)
    return render_template("produto_detalhe.html", produto=item)


@app.route("/carrinho")
def carrinho_view():
    entrega = 8 if carrinho_atual() else 0
    return render_template("carrinho.html", entrega=entrega)


@app.route("/carrinho/adicionar/<produto_id>", methods=["POST"])
def carrinho_adicionar(produto_id):
    user = usuario_logado()
    if user and user.get("papel") == "admin":
        flash("Administradores não podem fazer compras.", "erro")
        return redirect(request.form.get("voltar") or url_for("cardapio"))

    item = buscar_produto(produto_id)
    if not item:
        abort(404)
    if not item.get("disponivel", True):
        flash(f"{item['nome']} está indisponível no momento.", "erro")
        return redirect(request.form.get("voltar") or url_for("cardapio"))

    qtd = max(1, int(request.form.get("qtd", 1)))
    itens = carrinho_atual()
    for linha in itens:
        if linha["id"] == produto_id:
            linha["qtd"] += qtd
            break
    else:
        itens.append(
            {
                "id": item["id"],
                "nome": item["nome"],
                "preco": item["preco"],
                "imagem": item["imagem"],
                "qtd": qtd,
            }
        )
    gravar_carrinho(itens)
    flash(f"{qtd}x {item['nome']} no carrinho", "sucesso")
    return redirect(request.form.get("voltar") or url_for("cardapio"))


@app.route("/carrinho/quantidade/<produto_id>", methods=["POST"])
def carrinho_quantidade(produto_id):
    qtd = int(request.form.get("qtd", 1))
    itens = [
        {**i, "qtd": max(0, qtd)} if i["id"] == produto_id else i for i in carrinho_atual()
    ]
    gravar_carrinho([i for i in itens if i["qtd"] > 0])
    return redirect(url_for("carrinho_view"))


@app.route("/carrinho/remover/<produto_id>", methods=["POST"])
def carrinho_remover(produto_id):
    gravar_carrinho([i for i in carrinho_atual() if i["id"] != produto_id])
    return redirect(request.form.get("voltar") or url_for("carrinho_view"))


@app.route("/carrinho/finalizar", methods=["POST"])
def carrinho_finalizar():
    return redirect(url_for("checkout"))


@app.route("/login", methods=["GET", "POST"])
def login():
    erro = ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""
        if "@" not in email or len(senha) < 6:
            erro = "Informe um e-mail válido e uma senha com pelo menos 6 caracteres."
        else:
            for usuario in ler_json("usuarios.json"):
                if usuario["email"].lower() == email and usuario["senha"] == senha:
                    session["usuario_id"] = usuario["id"]
                    flash("Bem-vindo(a) de volta!", "sucesso")
                    if usuario.get("papel") == "admin":
                        return redirect(url_for("admin"))
                    return redirect(url_for("inicio"))
            erro = "E-mail ou senha incorretos."
    return render_template("login.html", erro=erro)


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    erro = ""
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        email = (request.form.get("email") or "").strip()
        telefone = (request.form.get("telefone") or "").strip()
        senha = request.form.get("senha") or ""
        receber_email = request.form.get("receber_email") == "on"
        usuarios = ler_json("usuarios.json")

        if len(nome) < 3:
            erro = "Informe seu nome completo (mínimo 3 caracteres)."
        elif "@" not in email:
            erro = "Informe um e-mail válido."
        elif len("".join(c for c in telefone if c.isdigit())) < 10:
            erro = "Informe um telefone válido com DDD."
        elif len(senha) < 6:
            erro = "A senha deve ter pelo menos 6 caracteres."
        elif any(u["email"].lower() == email.lower() for u in usuarios):
            erro = "Este e-mail já está cadastrado."
        else:
            novo = {
                "id": f"u-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "nome": nome,
                "email": email,
                "telefone": telefone,
                "senha": senha,
                "papel": "cliente",
                "receber_email": receber_email,
            }
            usuarios.append(novo)
            gravar_json("usuarios.json", usuarios)
            session["usuario_id"] = novo["id"]
            flash("Conta criada com sucesso!", "sucesso")
            return redirect(url_for("inicio"))
    return render_template("cadastro.html", erro=erro)


@app.route("/sair")
def sair():
    session.pop("usuario_id", None)
    flash("Você saiu da conta.", "sucesso")
    return redirect(url_for("inicio"))


@app.route("/pedidos")
def meus_pedidos():
    usuario = usuario_logado()
    meus = (
        [p for p in ler_json("pedidos.json") if p["email"] == usuario["email"]]
        if usuario
        else []
    )
    return render_template("pedidos.html", pedidos=meus)


@app.route("/pedidos/confirmar/<pedido_id>", methods=["POST"])
def confirmar_entrega(pedido_id):
    usuario = usuario_logado()
    if not usuario:
        flash("Faça login para confirmar.", "erro")
        return redirect(url_for("login"))

    pedidos = ler_json("pedidos.json")
    for i, pedido in enumerate(pedidos):
        if pedido["id"] == pedido_id and pedido["email"] == usuario["email"]:
            if pedido["status"] == "Saiu para entrega":
                pedido["status"] = "Entregue"
                pedidos[i] = pedido
                gravar_json("pedidos.json", pedidos)
                flash("Entrega confirmada! Obrigado pela preferência.", "sucesso")
                return redirect(url_for("meus_pedidos"))
            else:
                flash("Pedido ainda não saiu para entrega.", "erro")
                return redirect(url_for("meus_pedidos"))
    flash("Pedido não encontrado.", "erro")
    return redirect(url_for("meus_pedidos"))


@app.route("/contato", methods=["GET", "POST"])
def contato():
    erro = ""
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        telefone = (request.form.get("telefone") or "").strip()
        mensagem = (request.form.get("mensagem") or "").strip()

        if len(nome) < 3:
            erro = "Informe seu nome (mínimo 3 caracteres)."
        elif len("".join(c for c in telefone if c.isdigit())) < 10:
            erro = "Informe um telefone válido com DDD."
        elif not 10 <= len(mensagem) <= 1000:
            erro = "A mensagem deve ter entre 10 e 1000 caracteres."
        else:
            mensagens = ler_json("mensagens.json")
            mensagens.insert(
                0,
                {
                    "id": f"m-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    "nome": nome,
                    "telefone": telefone,
                    "mensagem": mensagem,
                    "data": datetime.now().isoformat(timespec="seconds"),
                },
            )
            gravar_json("mensagens.json", mensagens)
            flash("Mensagem enviada! Responderemos em breve.", "sucesso")
            return redirect(url_for("contato"))
    return render_template("contato.html", erro=erro)


@app.route("/sobre")
def sobre():
    return render_template("sobre.html")


# ======================================================================
# CHAT E AJUDA
# ======================================================================

@app.route("/chat")
def chat():
    usuario = usuario_logado()
    if not usuario:
        flash("Faça login para acessar o chat.", "erro")
        return redirect(url_for("login"))

    comentarios = ler_json("comentarios.json")
    if usuario.get("papel") == "admin":
        return render_template("chat.html", comentarios=comentarios, is_admin=True)
    else:
        meus_comentarios = [c for c in comentarios if c["email"] == usuario["email"]]
        return render_template("chat.html", comentarios=meus_comentarios, is_admin=False)


@app.route("/chat/enviar", methods=["POST"])
def chat_enviar():
    usuario = usuario_logado()
    if not usuario:
        flash("Faça login para enviar mensagem.", "erro")
        return redirect(url_for("login"))

    mensagem = (request.form.get("mensagem") or "").strip()
    if len(mensagem) < 3:
        flash("Mensagem muito curta.", "erro")
        return redirect(url_for("chat"))

    comentarios = ler_json("comentarios.json")
    novo = {
        "id": f"c-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "nome": usuario["nome"],
        "email": usuario["email"],
        "mensagem": mensagem,
        "data": datetime.now().isoformat(timespec="seconds"),
        "resposta": None,
    }
    comentarios.insert(0, novo)
    gravar_json("comentarios.json", comentarios)
    flash("Mensagem enviada!", "sucesso")
    return redirect(url_for("chat"))


@app.route("/admin/chat/responder/<comentario_id>", methods=["POST"])
@somente_admin
def admin_responder_chat(comentario_id):
    resposta = (request.form.get("resposta") or "").strip()
    if len(resposta) < 3:
        flash("Resposta muito curta.", "erro")
        return redirect(url_for("admin"))

    comentarios = ler_json("comentarios.json")
    for c in comentarios:
        if c["id"] == comentario_id:
            c["resposta"] = {
                "mensagem": resposta,
                "data": datetime.now().isoformat(timespec="seconds"),
                "admin": usuario_logado()["nome"],
            }
            gravar_json("comentarios.json", comentarios)
            flash("Resposta enviada!", "sucesso")
            return redirect(url_for("admin"))
    flash("Comentário não encontrado.", "erro")
    return redirect(url_for("admin"))


@app.route("/admin/chat/excluir/<comentario_id>", methods=["POST"])
@somente_admin
def admin_excluir_comentario(comentario_id):
    comentarios = [c for c in ler_json("comentarios.json") if c["id"] != comentario_id]
    gravar_json("comentarios.json", comentarios)
    flash("Comentário excluído.", "sucesso")
    return redirect(url_for("admin"))


@app.route("/ajuda")
def ajuda():
    usuario = usuario_logado()
    if not usuario:
        flash("Faça login para acessar a central de ajuda.", "erro")
        return redirect(url_for("login"))

    duvidas = ler_json("ajuda.json")
    if usuario.get("papel") == "admin":
        return render_template("ajuda.html", duvidas=duvidas, is_admin=True)
    else:
        minhas_duvidas = [d for d in duvidas if d["email"] == usuario["email"]]
        return render_template("ajuda.html", duvidas=minhas_duvidas, is_admin=False)


@app.route("/ajuda/enviar", methods=["POST"])
def ajuda_enviar():
    usuario = usuario_logado()
    if not usuario:
        flash("Faça login para enviar dúvida.", "erro")
        return redirect(url_for("login"))

    duvida = (request.form.get("duvida") or "").strip()
    if len(duvida) < 10:
        flash("Dúvida muito curta (mínimo 10 caracteres).", "erro")
        return redirect(url_for("ajuda"))

    duvidas = ler_json("ajuda.json")
    nova = {
        "id": f"a-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "nome": usuario["nome"],
        "email": usuario["email"],
        "duvida": duvida,
        "data": datetime.now().isoformat(timespec="seconds"),
        "resposta": None,
    }
    duvidas.insert(0, nova)
    gravar_json("ajuda.json", duvidas)
    flash("Dúvida enviada!", "sucesso")
    return redirect(url_for("ajuda"))


@app.route("/admin/ajuda/responder/<duvida_id>", methods=["POST"])
@somente_admin
def admin_responder_ajuda(duvida_id):
    resposta = (request.form.get("resposta") or "").strip()
    if len(resposta) < 3:
        flash("Resposta muito curta.", "erro")
        return redirect(url_for("admin"))

    duvidas = ler_json("ajuda.json")
    for d in duvidas:
        if d["id"] == duvida_id:
            d["resposta"] = {
                "mensagem": resposta,
                "data": datetime.now().isoformat(timespec="seconds"),
                "admin": usuario_logado()["nome"],
            }
            gravar_json("ajuda.json", duvidas)
            flash("Resposta enviada!", "sucesso")
            return redirect(url_for("admin"))
    flash("Dúvida não encontrada.", "erro")
    return redirect(url_for("admin"))


@app.route("/admin/ajuda/excluir/<duvida_id>", methods=["POST"])
@somente_admin
def admin_excluir_duvida(duvida_id):
    duvidas = [d for d in ler_json("ajuda.json") if d["id"] != duvida_id]
    gravar_json("ajuda.json", duvidas)
    flash("Dúvida excluída.", "sucesso")
    return redirect(url_for("admin"))


# ======================================================================
# ADMIN
# ======================================================================

@app.route("/admin")
@somente_admin
def admin():
    return render_template(
        "admin.html",
        produtos=todos_produtos(),
        pedidos=ler_json("pedidos.json"),
        usuarios=ler_json("usuarios.json"),
        mensagens=ler_json("mensagens.json"),
        comentarios=ler_json("comentarios.json"),
        duvidas=ler_json("ajuda.json"),
        config=ler_json("config.json"),
        pagamentos=ler_json("pagamentos.json"),
    )


@app.route("/admin/pedido/<pedido_id>/status", methods=["POST"])
@somente_admin
def admin_alterar_status_pedido(pedido_id):
    novo_status = request.form.get("status")
    if novo_status not in ["Saiu para entrega", "Entregue"]:
        flash("Status inválido.", "erro")
        return redirect(url_for("admin"))

    pedidos = ler_json("pedidos.json")
    for i, pedido in enumerate(pedidos):
        if pedido["id"] == pedido_id:
            pedido["status"] = novo_status
            pedidos[i] = pedido
            gravar_json("pedidos.json", pedidos)
            flash(f"Pedido {pedido_id} atualizado para: {novo_status}.", "sucesso")
            return redirect(url_for("admin"))
    flash("Pedido não encontrado.", "erro")
    return redirect(url_for("admin"))


@app.route("/admin/produto/novo", methods=["POST"])
@somente_admin
def admin_novo_produto():
    nome = (request.form.get("nome") or "").strip()
    if not nome:
        flash("Informe o nome do produto.", "erro")
        return redirect(url_for("admin"))

    imagem = request.form.get("imagem") or "salgados"
    if "foto" in request.files and request.files["foto"].filename:
        arquivo = request.files["foto"]
        if arquivo and arquivo.filename:
            ext = arquivo.filename.rsplit(".", 1)[-1].lower()
            if ext in ["png", "jpg", "jpeg", "gif", "webp"]:
                nome_arquivo = f"{uuid.uuid4().hex}.{ext}"
                caminho = os.path.join(app.config["UPLOAD_FOLDER"], nome_arquivo)
                arquivo.save(caminho)
                imagem = f"uploads/{nome_arquivo}"
            else:
                flash("Formato de imagem não suportado.", "erro")
                return redirect(url_for("admin"))

    salvar_produto(
        {
            "id": f"p-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "nome": nome,
            "categoria": (request.form.get("categoria") or "Salgados").strip(),
            "descricao": (request.form.get("descricao") or "").strip(),
            "preco": float(request.form.get("preco") or 0),
            "imagem": imagem,
            "destaque": False,
            "disponivel": True,
        }
    )
    flash("Produto cadastrado!", "sucesso")
    return redirect(url_for("admin"))


@app.route("/admin/produto/<produto_id>", methods=["GET", "POST"])
@somente_admin
def admin_editar_produto(produto_id):
    item = buscar_produto(produto_id)
    if not item:
        abort(404)
    if request.method == "POST":
        imagem = item["imagem"]
        if "foto" in request.files and request.files["foto"].filename:
            arquivo = request.files["foto"]
            if arquivo and arquivo.filename:
                ext = arquivo.filename.rsplit(".", 1)[-1].lower()
                if ext in ["png", "jpg", "jpeg", "gif", "webp"]:
                    nome_arquivo = f"{uuid.uuid4().hex}.{ext}"
                    caminho = os.path.join(app.config["UPLOAD_FOLDER"], nome_arquivo)
                    arquivo.save(caminho)
                    imagem = f"uploads/{nome_arquivo}"
                else:
                    flash("Formato de imagem não suportado.", "erro")
                    return redirect(url_for("admin_editar_produto", produto_id=produto_id))

        item.update(
            {
                "nome": (request.form.get("nome") or item["nome"]).strip(),
                "categoria": (request.form.get("categoria") or item["categoria"]).strip(),
                "descricao": (request.form.get("descricao") or item["descricao"]).strip(),
                "preco": float(request.form.get("preco") or item["preco"]),
                "imagem": imagem,
                "disponivel": request.form.get("disponivel") == "on",
            }
        )
        salvar_produto(item)
        flash("Produto atualizado!", "sucesso")
        return redirect(url_for("admin"))
    return render_template("admin_produto.html", produto=item)


@app.route("/admin/produto/<produto_id>/excluir", methods=["POST"])
@somente_admin
def admin_excluir_produto(produto_id):
    excluir_produto(produto_id)
    flash("Produto excluído.", "sucesso")
    return redirect(url_for("admin"))


@app.route("/admin/usuario/<usuario_id>/excluir", methods=["POST"])
@somente_admin
def admin_excluir_usuario(usuario_id):
    atual = usuario_logado()
    if atual and atual["id"] == usuario_id:
        flash("Você não pode excluir a própria conta.", "erro")
        return redirect(url_for("admin"))
    usuarios = [u for u in ler_json("usuarios.json") if u["id"] != usuario_id]
    gravar_json("usuarios.json", usuarios)
    flash("Usuário removido.", "sucesso")
    return redirect(url_for("admin"))


@app.route("/admin/config/mapa", methods=["POST"])
@somente_admin
def admin_salvar_mapa():
    mapa_url = (request.form.get("mapa_url") or "").strip()
    config = ler_json("config.json")
    if config:
        config[0]["mapa_url"] = mapa_url
    else:
        config = [{"mapa_url": mapa_url}]
    gravar_json("config.json", config)
    flash("Localização do mapa atualizada!", "sucesso")
    return redirect(url_for("admin"))


# ======================================================================
# ENVIO DE E-MAIL
# ======================================================================

@app.route("/admin/enviar-email", methods=["POST"])
@somente_admin
def admin_enviar_email():
    usuario = usuario_logado()
    if not usuario:
        flash("Você precisa estar logado como admin.", "erro")
        return redirect(url_for("login"))

    assunto = (request.form.get("assunto") or "").strip()
    corpo = (request.form.get("corpo") or "").strip()

    if not assunto or not corpo:
        flash("Preencha todos os campos: assunto e mensagem.", "erro")
        return redirect(url_for("admin"))

    usuarios = ler_json("usuarios.json")
    destinatarios = [u["email"] for u in usuarios if u.get("receber_email") == True]

    if not destinatarios:
        flash("Nenhum usuário cadastrado aceitou receber e-mails.", "erro")
        return redirect(url_for("admin"))

    try:
        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASSWORD)

        enviados = 0
        erros = []

        for email in destinatarios:
            try:
                msg = MIMEMultipart()
                msg["From"] = EMAIL_USER
                msg["To"] = email
                msg["Subject"] = assunto

                corpo_html = f"""
                <html>
                <head>
                    <style>
                        body {{ font-family: Arial, sans-serif; color: #333; }}
                        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                        .header {{ background: #4a9e8f; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                        .content {{ background: #f5f9f8; padding: 30px; border-radius: 0 0 10px 10px; }}
                        .footer {{ text-align: center; padding: 10px; color: #666; font-size: 12px; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h2>🥨 CROCH Salgadaria</h2>
                        </div>
                        <div class="content">
                            <p>{corpo.replace(chr(10), '<br>')}</p>
                        </div>
                        <div class="footer">
                            <p>© {datetime.now().year} CROCH Salgadaria - Todos os direitos reservados</p>
                            <p>Você recebeu este email porque autorizou em nosso cadastro.</p>
                        </div>
                    </div>
                </body>
                </html>
                """

                msg.attach(MIMEText(corpo_html, "html"))
                server.send_message(msg)
                enviados += 1

            except Exception as e:
                erros.append(f"{email}: {str(e)}")

        server.quit()

        if erros:
            flash(f"E-mail enviado para {enviados} cliente(s). Erros: {', '.join(erros[:3])}", "erro")
        else:
            flash(f"E-mail enviado com sucesso para {enviados} cliente(s) que autorizaram recebimento!", "sucesso")

    except Exception as e:
        flash(f"Erro ao enviar e-mails: {str(e)}", "erro")

    return redirect(url_for("admin"))


# ============================================================
# CRIA ARQUIVOS SE NÃO EXISTIREM
# ============================================================

if not os.path.exists(os.path.join(DADOS_DIR, "pagamentos.json")):
    gravar_json("pagamentos.json", [])

if not os.path.exists(os.path.join(DADOS_DIR, "produtos.json")):
    produtos_padrao = [
        {
            "id": "p-001",
            "nome": "Coxinha de Frango",
            "categoria": "Salgados",
            "descricao": "Coxinha tradicional com recheio de frango desfiado e catupiry",
            "preco": 5.50,
            "imagem": "coxinha",
            "destaque": True,
            "disponivel": True
        },
        {
            "id": "p-002",
            "nome": "Kibe",
            "categoria": "Salgados",
            "descricao": "Kibe assado com recheio de carne e hortelã",
            "preco": 5.00,
            "imagem": "salgados",
            "destaque": False,
            "disponivel": True
        },
        {
            "id": "p-003",
            "nome": "Esfiha de Carne",
            "categoria": "Salgados",
            "descricao": "Esfiha aberta com carne moída, tomate e cebola",
            "preco": 6.00,
            "imagem": "salgados",
            "destaque": False,
            "disponivel": True
        },
        {
            "id": "p-004",
            "nome": "Pão de Queijo",
            "categoria": "Salgados",
            "descricao": "Pão de queijo mineiro quentinho e macio",
            "preco": 4.50,
            "imagem": "salgados",
            "destaque": False,
            "disponivel": True
        }
    ]
    gravar_json("produtos.json", produtos_padrao)

if not os.path.exists(os.path.join(DADOS_DIR, "combos.json")):
    combos_padrao = [
        {
            "id": "combo-20",
            "nome": "Combo 20",
            "categoria": "Combos",
            "descricao": "20 salgados sortidos, feitos na hora. Perfeito para pequenos encontros.",
            "preco": 29.90,
            "unidades": 20,
            "imagem": "caixa",
            "destaque": False,
            "disponivel": True
        },
        {
            "id": "combo-50",
            "nome": "Combo 50",
            "categoria": "Combos",
            "descricao": "50 salgados sortidos com mais variedade para reuniões e comemorações.",
            "preco": 64.90,
            "unidades": 50,
            "imagem": "caixa",
            "destaque": False,
            "disponivel": True
        },
        {
            "id": "combo-100",
            "nome": "Combo 100",
            "categoria": "Combos",
            "descricao": "100 salgados sortidos com ótimo custo-benefício para grandes festas.",
            "preco": 119.90,
            "unidades": 100,
            "imagem": "combo-festa",
            "destaque": False,
            "disponivel": True
        },
        {
            "id": "combo-festa",
            "nome": "Combo Festa",
            "categoria": "Combos",
            "descricao": "200 salgados sortidos + molhos especiais. O sabor que conquista todos os convidados.",
            "preco": 229.90,
            "unidades": 200,
            "imagem": "combo-festa",
            "destaque": True,
            "disponivel": True
        }
    ]
    gravar_json("combos.json", combos_padrao)


@app.errorhandler(404)
def pagina_nao_encontrada(_erro):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True, port=5000)  
