# CROCH Salgadaria — versão Flask

Sistema de pedidos online da CROCH Salgadaria em **Python + Flask + Jinja2 + JSON**,
com **HTML5, CSS3, Bootstrap 5 e JavaScript** no front-end. Não usa banco de dados:
todos os dados ficam em arquivos JSON na pasta `dados/`.

## Como executar

```bash
cd flask_croch
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Acesse http://localhost:5000

Login de teste (admin): `admin@croch.com` / `admin123`
Login de teste (cliente): `cliente@croch.com` / `cliente123`

## Estrutura

```
flask_croch/
├── app.py                  # rotas, sessão, regras de negócio
├── requirements.txt
├── dados/                  # "banco de dados" em JSON
│   ├── produtos.json
│   ├── combos.json
│   ├── usuarios.json
│   ├── pedidos.json
│   └── mensagens.json
├── templates/              # Jinja2 (HTML5 + Bootstrap 5)
│   ├── base.html           # layout, navbar, rodapé, acessibilidade
│   ├── _macros.html        # macro do cartão de produto
│   ├── index.html  cardapio.html  produto.html  carrinho.html
│   ├── login.html  cadastro.html  pedidos.html  contato.html
│   ├── sobre.html  admin.html  admin_produto.html
│   └── 404.html  restrito.html
└── static/
    ├── css/estilo.css      # design system (mesmas cores do protótipo)
    ├── js/app.js           # acessibilidade, busca com sugestões, abas, topo
    └── img/                # logo, coxinha, caixa, refrigerante, salgados...
```

## Funcionalidades

- Catálogo com busca, filtro por categoria e página de detalhe do produto
- Carrinho em sessão: adicionar, alterar quantidade, remover e finalizar pedido
- Cadastro, login e logout com validação (dados gravados em `usuarios.json`)
- Histórico de pedidos por cliente
- Formulário de contato salvando mensagens em `mensagens.json`
- Painel administrativo: CRUD de produtos, pedidos, usuários e mensagens
- Acessibilidade: pular para conteúdo, alto contraste, tema escuro, tamanho de fonte,
  navegação por teclado e atalho `/` para a busca
- Rota `GET /api/produtos?q=` usada pelo autocomplete em JavaScript
