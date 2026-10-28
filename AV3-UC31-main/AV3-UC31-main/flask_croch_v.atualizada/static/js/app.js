/* CROCH Salgadaria — comportamentos de interface (acessibilidade, busca,
   voltar ao topo, avisos e abas do painel administrativo). */

(function () {
  "use strict";

  const corpo = document.body;
  const CHAVE = "croch:preferencias";

  /* ------------------------------------------------ preferências salvas */
  const prefs = Object.assign(
    { escuro: false, contraste: false, fonte: 100 },
    JSON.parse(localStorage.getItem(CHAVE) || "{}")
  );

  function aplicarPreferencias() {
    corpo.classList.toggle("escuro", prefs.escuro);
    corpo.classList.toggle("contraste", prefs.contraste);
    document.documentElement.style.setProperty("--fonte-base", prefs.fonte + "%");
    localStorage.setItem(CHAVE, JSON.stringify(prefs));
  }
  aplicarPreferencias();

  document.querySelectorAll("[data-acao]").forEach(function (botao) {
    botao.addEventListener("click", function () {
      const acao = botao.dataset.acao;
      if (acao === "tema") prefs.escuro = !prefs.escuro;
      if (acao === "contraste") prefs.contraste = !prefs.contraste;
      if (acao === "fonte-mais") prefs.fonte = Math.min(140, prefs.fonte + 10);
      if (acao === "fonte-menos") prefs.fonte = Math.max(80, prefs.fonte - 10);
      if (acao === "fonte-padrao") prefs.fonte = 100;
      aplicarPreferencias();
    });
  });

  /* ------------------------------------------------------ sombra ao rolar */
  const cabecalho = document.querySelector(".cabecalho");
  const botaoTopo = document.querySelector(".voltar-topo");

  window.addEventListener("scroll", function () {
    if (cabecalho) cabecalho.classList.toggle("rolando", window.scrollY > 8);
    if (botaoTopo) botaoTopo.classList.toggle("visivel", window.scrollY > 400);
  });

  if (botaoTopo) {
    botaoTopo.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  /* ------------------------------------------- busca com sugestões (AJAX) */
  const campoBusca = document.getElementById("busca-cabecalho");
  const listaSugestoes = document.getElementById("sugestoes");

  if (campoBusca && listaSugestoes) {
    let temporizador;

    campoBusca.addEventListener("input", function () {
      clearTimeout(temporizador);
      const termo = campoBusca.value.trim();
      if (termo.length < 2) {
        listaSugestoes.hidden = true;
        listaSugestoes.innerHTML = "";
        return;
      }
      temporizador = setTimeout(function () {
        fetch("/api/produtos?q=" + encodeURIComponent(termo))
          .then(function (r) { return r.json(); })
          .then(function (itens) {
            if (!itens.length) {
              listaSugestoes.hidden = true;
              return;
            }
            listaSugestoes.innerHTML = itens
              .map(function (p) {
                const preco = p.preco.toFixed(2).replace(".", ",");
                return (
                  '<li><a href="/produto/' + p.id + '"><span>' + p.nome +
                  '</span><strong>R$ ' + preco + "</strong></a></li>"
                );
              })
              .join("");
            listaSugestoes.hidden = false;
          })
          .catch(function () { listaSugestoes.hidden = true; });
      }, 180);
    });

    document.addEventListener("click", function (evento) {
      if (!listaSugestoes.contains(evento.target) && evento.target !== campoBusca) {
        listaSugestoes.hidden = true;
      }
    });

    // Atalho "/" foca a busca
    document.addEventListener("keydown", function (evento) {
      if (evento.key === "/" && document.activeElement.tagName !== "INPUT" &&
          document.activeElement.tagName !== "TEXTAREA") {
        evento.preventDefault();
        campoBusca.focus();
      }
      if (evento.key === "Escape") listaSugestoes.hidden = true;
    });
  }

  /* ------------------------------------------------------- avisos (toast) */
  document.querySelectorAll(".toast-croch").forEach(function (aviso, indice) {
    aviso.style.top = 1 + indice * 4.5 + "rem";
    setTimeout(function () { aviso.remove(); }, 4000);
  });

  /* ------------------------------------------------ abas do painel admin */
  const abas = document.querySelectorAll(".aba-croch");
  if (abas.length) {
    abas.forEach(function (aba) {
      aba.addEventListener("click", function () {
        abas.forEach(function (b) {
          b.classList.remove("ativa");
          b.setAttribute("aria-selected", "false");
        });
        aba.classList.add("ativa");
        aba.setAttribute("aria-selected", "true");
        document.querySelectorAll("[data-painel]").forEach(function (painel) {
          painel.hidden = painel.dataset.painel !== aba.dataset.aba;
        });
      });
    });
  }
})();
