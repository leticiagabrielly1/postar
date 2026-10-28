import os
import json
import secrets
import sqlite3
from pathlib import Path
from functools import wraps
from decimal import Decimal, InvalidOperation
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

ROOT = Path(__file__).resolve().parent
app = Flask(__name__)
(ROOT / 'instance').mkdir(exist_ok=True)
key_file = ROOT / 'instance' / 'secret.key'
if not key_file.exists():
    try:
        with key_file.open('x') as f:
            f.write(secrets.token_hex(32))
        key_file.chmod(0o600)
    except FileExistsError:
        pass
app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY') or key_file.read_text(),
                  DATABASE=str(ROOT / 'instance' / 'rede.db'), SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE='Lax', MAX_CONTENT_LENGTH=1024 * 1024)
PONTOS = ['CRAS Centro', 'Escola Municipal Esperança', 'Igreja Solidária', 'ONG Mãos Unidas', 'Posto de Saúde Bairro Norte']
ALIMENTOS = ['Arroz', 'Feijão', 'Óleo', 'Açúcar', 'Macarrão', 'Café', 'Leite', 'Farinha', 'Sal', 'Biscoito', 'Milho', 'Ervilha', 'Molho', 'Aveia', 'Fubá', 'Sardinha', 'Atum', 'Achocolatado', 'Macarrão instantâneo', 'Canjica']
HIGIENE = ['Sabonete', 'Pasta de dente', 'Papel higiênico', 'Shampoo', 'Detergente']
ROUPAS = ['Camisa', 'Calça', 'Sapato']
PRODUTOS = ALIMENTOS + HIGIENE
TIPOS = {'Infantil': (20, ['Leite', 'Achocolatado', 'Biscoito']), 'Emergencial': (18, ['Arroz', 'Feijão', 'Óleo']), 'Nutricional': (15, ['Arroz', 'Feijão', 'Aveia', 'Leite'])}
ICONES = {'Arroz':'🍚','Feijão':'🫘','Óleo':'🫙','Açúcar':'🥣','Macarrão':'🍝','Café':'☕','Leite':'🥛','Farinha':'🌾','Sal':'🧂','Biscoito':'🍪','Milho':'🌽','Ervilha':'🫛','Molho':'🥫','Aveia':'🌾','Fubá':'🌽','Sardinha':'🐟','Atum':'🐟','Achocolatado':'🍫','Macarrão instantâneo':'🍜','Canjica':'🥣','Sabonete':'🧼','Pasta de dente':'🪥','Papel higiênico':'🧻','Shampoo':'🧴','Detergente':'🫧','Camisa':'👕','Calça':'👖','Sapato':'👟'}

def db():
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'], timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db

@app.teardown_appcontext
def close_db(error):
    connection = g.pop('db', None)
    if connection is not None:
        connection.close()

def init_db():
    c = db()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS usuarios(id INTEGER PRIMARY KEY, nome TEXT NOT NULL, cpf TEXT UNIQUE NOT NULL, telefone TEXT NOT NULL, senha TEXT NOT NULL, moradores INTEGER NOT NULL, criancas INTEGER NOT NULL, renda INTEGER NOT NULL, perfil TEXT NOT NULL, higiene INTEGER NOT NULL, codigo TEXT UNIQUE NOT NULL, ponto TEXT NOT NULL, admin INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS estoque(ponto TEXT NOT NULL, produto TEXT NOT NULL, quantidade INTEGER NOT NULL CHECK(quantidade>=0), PRIMARY KEY(ponto,produto));
    CREATE TABLE IF NOT EXISTS movimentos(id INTEGER PRIMARY KEY, usuario INTEGER NOT NULL REFERENCES usuarios(id), tipo TEXT NOT NULL, ponto TEXT NOT NULL, itens TEXT NOT NULL DEFAULT '{}', valor INTEGER NOT NULL DEFAULT 0, codigo TEXT UNIQUE NOT NULL, criado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE UNIQUE INDEX IF NOT EXISTS cesta_unica ON movimentos(usuario) WHERE tipo='Cesta';
    ''')
    quantidades = [(20,15,10),(10,8,5),(12,10,7),(18,12,9),(14,11,6)]
    for i, ponto in enumerate(PONTOS):
        for produto in PRODUTOS + ROUPAS:
            quantidade = quantidades[i][ROUPAS.index(produto)] if produto in ROUPAS else 50
            c.execute('INSERT OR IGNORE INTO estoque VALUES(?,?,?)', (ponto,produto,quantidade))
    c.commit()

def codigo(prefix):
    return prefix + '-' + secrets.token_hex(5).upper()

def dinheiro(value):
    try:
        n = Decimal(str(value).replace(',', '.'))
        if not n.is_finite() or n < 0 or n > 100000000 or n.as_tuple().exponent < -2:
            raise ValueError
        return int(n * 100)
    except (InvalidOperation, ValueError):
        raise ValueError('Informe um valor válido, com até duas casas decimais.')

@app.template_filter('brl')
def brl(value):
    return ('R$ ' + f'{value / 100:,.2f}').replace(',', 'X').replace('.', ',').replace('X', '.')

@app.before_request
def prepare():
    g.user = db().execute('SELECT * FROM usuarios WHERE id=?', (session.get('uid'),)).fetchone()
    if 'csrf' not in session:
        session['csrf'] = secrets.token_hex(32)
    if request.method == 'POST' and not secrets.compare_digest(session['csrf'], request.form.get('csrf','')):
        abort(400, 'Sua sessão expirou. Recarregue a página e tente novamente.')

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not g.user:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapped

@app.context_processor
def context():
    return dict(user=g.user, pontos=PONTOS, icones=ICONES, tipos=TIPOS)

@app.route('/')
def home():
    return redirect(url_for('painel' if g.user else 'login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        cpf = ''.join(x for x in request.form.get('cpf','') if x.isdigit())
        u = db().execute('SELECT * FROM usuarios WHERE cpf=?', (cpf,)).fetchone()
        if u and check_password_hash(u['senha'], request.form.get('senha','')):
            session.clear()
            session['uid'] = u['id']
            return redirect(url_for('painel'))
        flash('CPF ou senha incorretos.', 'error')
    return render_template('auth.html', title='Bem-vindo à Rede Solidariza', cadastro=False)

@app.route('/cadastro', methods=['GET','POST'])
def cadastro():
    if request.method == 'POST':
        try:
            nome = request.form.get('nome','').strip()
            cpf = ''.join(x for x in request.form.get('cpf','') if x.isdigit())
            telefone = ''.join(x for x in request.form.get('telefone','') if x.isdigit())
            senha = request.form.get('senha','')
            moradores = int(request.form.get('moradores','0'))
            criancas = int(request.form.get('criancas','0'))
            renda = dinheiro(request.form.get('renda',''))
            ponto = request.form.get('ponto')
            if not 2 <= len(nome) <= 100 or len(cpf) != 11 or len(telefone) not in (10,11):
                raise ValueError('Confira nome, CPF (11 dígitos) e telefone com DDD.')
            if not 8 <= len(senha) <= 128:
                raise ValueError('A senha deve ter de 8 a 128 caracteres.')
            if not 1 <= moradores <= 100 or not 0 <= criancas <= moradores:
                raise ValueError('Confira a quantidade de moradores e crianças.')
            if ponto not in PONTOS or request.form.get('consentimento') != 'on':
                raise ValueError('Escolha um ponto e confirme o consentimento.')
            perfil = 'Doador' if renda >= 80000 * moradores else 'Beneficiário'
            with db():
                cur = db().execute('INSERT INTO usuarios(nome,cpf,telefone,senha,moradores,criancas,renda,perfil,higiene,codigo,ponto) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (nome,cpf,telefone,generate_password_hash(senha),moradores,criancas,renda,perfil,int(renda <= 30000 * moradores),codigo('DOA' if perfil=='Doador' else 'REC'),ponto))
            session.clear()
            session['uid'] = cur.lastrowid
            return redirect(url_for('resultado'))
        except (ValueError, sqlite3.IntegrityError) as e:
            flash(str(e) if isinstance(e,ValueError) else 'Não foi possível cadastrar. Confira os dados ou tente entrar.', 'error')
    return render_template('auth.html', title='Vamos começar?', cadastro=True)

@app.route('/resultado')
@login_required
def resultado():
    return render_template('resultado.html', title='Resultado do cadastro')

@app.route('/painel')
@login_required
def painel():
    registros = db().execute('SELECT * FROM movimentos WHERE usuario=? ORDER BY id DESC', (g.user['id'],)).fetchall()
    cesta = next((r for r in registros if r['tipo']=='Cesta'), None)
    return render_template('painel.html', title='Meu painel', registros=registros, cesta=cesta,
                           itens=json.loads(cesta['itens']) if cesta else {}, total=sum(r['valor'] for r in registros))

def estoque_atual(ponto):
    return {r['produto']:r['quantidade'] for r in db().execute('SELECT * FROM estoque WHERE ponto=?',(ponto,))}

def registrar(tipo, ponto, itens, direction, valor=0):
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        for produto, qtd in itens.items():
            cur = c.execute('UPDATE estoque SET quantidade=quantidade+? WHERE ponto=? AND produto=? AND quantidade+?>=0', (direction*qtd,ponto,produto,direction*qtd))
            if cur.rowcount != 1:
                raise ValueError(f'Estoque insuficiente de {produto}. Nenhum item foi registrado.')
        cur = c.execute('INSERT INTO movimentos(usuario,tipo,ponto,itens,valor,codigo) VALUES(?,?,?,?,?,?)', (g.user['id'],tipo,ponto,json.dumps(itens,ensure_ascii=False),valor,codigo('RS')))
        c.commit()
        return cur.lastrowid
    except Exception:
        c.rollback()
        raise

@app.route('/cesta', methods=['GET','POST'])
@login_required
def cesta():
    if g.user['perfil'] != 'Beneficiário':
        abort(403)
    if db().execute("SELECT id FROM movimentos WHERE usuario=? AND tipo='Cesta'",(g.user['id'],)).fetchone():
        flash('Sua cesta já está registrada. Consulte o código no painel.', 'info')
        return redirect(url_for('painel'))
    tipo = request.values.get('tipo','Emergencial')
    if tipo not in TIPOS:
        abort(400)
    limite, obrigatorios = TIPOS[tipo]
    limite += 5 if g.user['criancas'] else 0
    extras = HIGIENE if g.user['higiene'] else []
    if request.method == 'POST':
        try:
            itens = {}
            for i, p in enumerate(PRODUTOS):
                n = int(request.form.get(f'q_{i}','0'))
                if n < 0 or n > limite:
                    raise ValueError('Quantidade fora do limite.')
                if n:
                    itens[p] = n
            for p in obrigatorios:
                if itens.get(p,0) < 1:
                    raise ValueError('Mantenha ao menos uma unidade de cada item obrigatório.')
            if sum(itens.values()) > limite:
                raise ValueError('O limite da cesta foi excedido.')
            for p in extras:
                itens[p] = itens.get(p,0) + 1
            mid = registrar('Cesta',g.user['ponto'],itens,-1)
            return redirect(url_for('comprovante',mid=mid))
        except (ValueError,sqlite3.IntegrityError) as e:
            flash(str(e) if isinstance(e,ValueError) else 'Esta cesta já foi registrada.', 'error')
    return render_template('cesta.html',title='Monte sua cesta',produtos=PRODUTOS, tipo=tipo,limite=limite,obrigatorios=obrigatorios,extras=extras,estoque=estoque_atual(g.user['ponto']))

@app.route('/movimentar/<modo>', methods=['GET','POST'])
@login_required
def movimentar(modo):
    opcoes = {'alimentos':('Doação de alimentos',PRODUTOS,1),'roupas':('Doação de roupas',ROUPAS,1),'pedido-roupas':('Pedido de roupas',ROUPAS,-1),'dinheiro':('Registro de valor',[],0)}
    if modo not in opcoes:
        abort(404)
    title, produtos, direction = opcoes[modo]
    if (direction >= 0 and g.user['perfil'] != 'Doador') or (direction < 0 and g.user['perfil'] != 'Beneficiário'):
        abort(403)
    ponto = request.form.get('ponto',g.user['ponto']) if direction >= 0 else g.user['ponto']
    if request.method == 'POST':
        try:
            if ponto not in PONTOS:
                raise ValueError('Escolha um ponto válido.')
            if direction >= 0 and not check_password_hash(g.user['senha'],request.form.get('senha','')):
                raise ValueError('Senha incorreta. Confirme sua senha para registrar.')
            itens = {}
            for i,p in enumerate(produtos):
                n = int(request.form.get(f'q_{i}','0'))
                if not 0 <= n <= 10000:
                    raise ValueError('Use quantidades de 0 a 10.000.')
                if n:
                    itens[p] = n
            valor = dinheiro(request.form.get('valor','0')) if modo=='dinheiro' else 0
            if not itens and valor <= 0:
                raise ValueError('Adicione itens ou informe um valor positivo.')
            mid = registrar(title,ponto,itens,direction,valor)
            return redirect(url_for('comprovante',mid=mid))
        except ValueError as e:
            flash(str(e),'error')
    return render_template('movimentar.html',title=title,modo=modo,produtos=produtos,direction=direction,estoque=estoque_atual(g.user['ponto']))

@app.route('/comprovante/<int:mid>')
@login_required
def comprovante(mid):
    r = db().execute('SELECT * FROM movimentos WHERE id=? AND usuario=?',(mid,g.user['id'])).fetchone()
    if not r:
        abort(404)
    return render_template('comprovante.html',title='Registro concluído',r=r,itens=json.loads(r['itens']))

@app.route('/pontos',methods=['GET','POST'])
@login_required
def pontos():
    if request.method == 'POST':
        p = request.form.get('ponto')
        if p not in PONTOS:
            abort(400)
        with db():
            db().execute('UPDATE usuarios SET ponto=? WHERE id=?',(p,g.user['id']))
        flash('Ponto atualizado para os próximos registros. Registros anteriores mantêm seu destino.','success')
        return redirect(url_for('pontos'))
    return render_template('pontos.html',title='Pontos de coleta')

@app.route('/estoque')
@login_required
def estoque():
    p = request.args.get('ponto',g.user['ponto'])
    if p not in PONTOS:
        abort(400)
    return render_template('estoque.html',title='Estoque por ponto',ponto=p,estoque=estoque_atual(p))

@app.route('/cadastros')
@login_required
def cadastros():
    if not g.user['admin']:
        abort(403)
    pessoas = db().execute('SELECT nome,perfil,moradores,criancas,ponto,codigo FROM usuarios ORDER BY nome').fetchall()
    valores = db().execute('SELECT u.nome, SUM(m.valor) AS total FROM movimentos m JOIN usuarios u ON u.id=m.usuario WHERE m.valor>0 GROUP BY u.id ORDER BY total DESC').fetchall()
    return render_template('cadastros.html',title='Cadastros',pessoas=pessoas,valores=valores,total=sum(r['total'] for r in valores))

@app.cli.command('tornar-admin')
def tornar_admin():
    import click
    cpf = click.prompt('CPF da conta que será administradora')
    with db():
        cur = db().execute('UPDATE usuarios SET admin=1 WHERE cpf=?',(cpf,))
    click.echo('Conta atualizada.' if cur.rowcount else 'Conta não encontrada.')

@app.route('/sair',methods=['POST'])
@login_required
def sair():
    session.clear()
    return redirect(url_for('login'))

@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
def error(e):
    return render_template('erro.html',title='Não foi possível continuar',error=e),e.code

with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(host='127.0.0.1',port=5000,debug=False)
