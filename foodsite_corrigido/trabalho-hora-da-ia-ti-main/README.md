# FoodSite — versão corrigida

## Rodar

```bash
python -m pip install -r requirements.txt
python app.py
```

Acesse http://127.0.0.1:5000/

Rotas: `/`, `/inicio`, `/sobre`, `/pedidos`, `/pizzaria/calabresa`, `/pizzaria/frango`, `/pizzaria/margherita`, `/contato`.

O formulário de contato é demonstrativo: **não envia nem salva mensagens**. Para produção, implemente persistência/envio, autenticação e proteção CSRF conforme o uso. Evite `debug=True` em produção.
