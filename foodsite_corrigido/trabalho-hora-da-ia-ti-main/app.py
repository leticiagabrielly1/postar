from flask import Flask, render_template, request

app = Flask(__name__)

PIZZAS = {
    "calabresa": {"nome": "Pizza de Calabresa", "imagem": "calabresa.jpg", "descricao": "Calabresa, queijo e molho de tomate."},
    "margherita": {"nome": "Pizza Margherita", "imagem": "margherita.jpg", "descricao": "Muçarela, tomate e manjericão."},
    "frango": {"nome": "Pizza de Frango", "imagem": "frango.jpg", "descricao": "Frango desfiado, queijo e temperos."},
}

@app.route("/")
@app.route("/inicio")
def home():
    return render_template("inicio.html")

@app.route("/sobre")
def sobre():
    return render_template("sobre.html")

@app.route("/pedidos")
def pedidos():
    return render_template("pedidos.html", pizzas=PIZZAS)

@app.route("/pizzaria/<sabor>")
def pizzaria(sabor):
    pizza = PIZZAS.get(sabor.lower())
    if pizza is None:
        return render_template("404.html"), 404
    return render_template("pizza_detalhe.html", pizza=pizza)

@app.route("/contato", methods=["GET", "POST"])
def contato():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip()
        mensagem = request.form.get("mensagem", "").strip()
        if not nome or not email or not mensagem:
            return render_template("contato.html", erro="Preencha todos os campos.", nome=nome, email=email, mensagem=mensagem), 400
        # Formulário demonstrativo: nenhuma mensagem é enviada ou armazenada.
        return render_template("contato.html", sucesso=True)
    return render_template("contato.html")

if __name__ == "__main__":
    app.run(debug=True)
