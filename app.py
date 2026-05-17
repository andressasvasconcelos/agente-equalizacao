"""
Agente de Equalização de Propostas FM-030 · Allwert
====================================================
Versão: 2.0
Correções aplicadas:
- Dados do fornecedor editáveis (campos individuais por fornecedor)
- Excluir/adicionar itens no mapa
- Menor preço por item destacado em verde automaticamente
- PDF gerado como HTML download (abre no browser → Ctrl+P → Salvar como PDF)
- Histórico de equalizações da sessão com redownload
"""

import streamlit as st
import anthropic
import base64
import json
import re
import os
import datetime

# ── Página ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Equalização FM-030 · Allwert",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');
html,body,[class*="css"]{font-family:'DM Sans',sans-serif}
.hbar{background:#0d5c4a;color:white;padding:14px 28px;border-bottom:3px solid #c9a227;
  display:flex;align-items:center;gap:14px;margin:-1rem -1rem 1.5rem -1rem}
.hlogo{font-size:22px;font-weight:700}.hlogo span{color:#c9a227}
.htitle{font-size:14px;color:rgba(255,255,255,.85)}
.hbadge{background:rgba(201,162,39,.2);border:1px solid #c9a227;color:#c9a227;
  font-size:11px;padding:2px 10px;border-radius:4px;margin-left:auto;font-family:monospace}
.steps{display:flex;background:white;border:1px solid #c8c8c8;border-radius:10px;
  overflow:hidden;margin-bottom:1.5rem;box-shadow:0 2px 8px rgba(0,0,0,.06)}
.step{flex:1;padding:11px 14px;border-right:1px solid #e8e8e8;display:flex;
  align-items:center;gap:8px;opacity:.4;font-size:12px}
.step:last-child{border-right:none}
.step.active{opacity:1;background:#f2faf7}
.step.done{opacity:.85}
.snum{width:22px;height:22px;border-radius:50%;background:#c8c8c8;color:#3d3d3d;
  display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0}
.step.active .snum,.step.done .snum{background:#0d5c4a;color:white}
.step.active span{color:#0d5c4a;font-weight:600}
.aok{background:#e6f4f0;border:1px solid #7ecfb8;color:#0d4a3b;
  padding:11px 15px;border-radius:8px;margin-bottom:12px;font-size:13px}
.awk{background:#fff7ed;border:1px solid #f5c26b;color:#7a4900;
  padding:11px 15px;border-radius:8px;margin-bottom:12px;font-size:13px}
.mapa-table{width:100%;border-collapse:collapse;font-size:12px}
.mapa-table th{background:#0d5c4a;color:white;padding:7px 9px;text-align:left;white-space:nowrap}
.mapa-table th.fh{background:#1a7a62;text-align:center}
.mapa-table th.fhw{background:#085041;text-align:center}
.mapa-table th.sh{background:#0f6e56;font-size:10px;text-align:right;padding:4px 8px}
.mapa-table td{padding:6px 9px;border-bottom:1px solid #f0f0f0;font-size:12px}
.mapa-table tr:hover td{background:#f8fffe}
.mapa-table td.mp{background:#eaf7f2;color:#0d5c4a;font-weight:700}
.mapa-table tfoot td{background:#0d5c4a;color:white;font-weight:700;padding:8px 9px}
.mapa-table tfoot td.win{background:#085041}
[data-testid="stSidebar"]{background:#f2faf7}
div[data-testid="stExpander"]{border:1px solid #e0e0e0;border-radius:8px;margin-bottom:8px}
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────
st.markdown("""
<div class="hbar">
  <div class="hlogo">W<span>ert</span></div>
  <div style="width:1px;height:20px;background:rgba(255,255,255,.2)"></div>
  <div class="htitle">Agente de Equalização de Propostas</div>
  <div class="hbadge">FM-030</div>
</div>
""", unsafe_allow_html=True)

# ── Session State ─────────────────────────────────────────────────
def init_state():
    for k, v in {
        "step": 1, "sc_num": "", "suppliers": [],
        "master_itens": [], "historico": [], "prices": {},
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ── Helpers ───────────────────────────────────────────────────────
def brl(v):
    try:
        n = float(v or 0)
        return f"R$ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

def esc(s):
    return str(s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def get_api_client():
    key = st.secrets.get("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
    return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()

def menor_idx_item(idx, n):
    best, best_si = float("inf"), -1
    for si in range(n):
        vu = st.session_state.prices.get(f"vu_{si}_{idx}", 0.0)
        q  = float(st.session_state.master_itens[idx].get("quantidade") or 0)
        t  = vu * q
        if vu > 0 and t > 0 and t < best:
            best, best_si = t, si
    return best_si

def calc_totais_forn(n):
    totais = []
    for si in range(n):
        total = sum(
            st.session_state.prices.get(f"vu_{si}_{idx}", 0.0)
            * float(st.session_state.master_itens[idx].get("quantidade") or 0)
            for idx in range(len(st.session_state.master_itens))
        )
        totais.append(total)
    return totais

def pre_popular_prices():
    """Preenche prices com valores extraídos pela IA (só se ainda não definido)."""
    for si, sup in enumerate(st.session_state.suppliers):
        for idx, it in enumerate(st.session_state.master_itens):
            key = f"vu_{si}_{idx}"
            if key not in st.session_state.prices:
                found = next(
                    (x for x in (sup.get("itens") or [])
                     if (x.get("descricao") or "").lower().strip()
                        == it["descricao"].lower().strip()),
                    None,
                )
                st.session_state.prices[key] = float(found.get("valor_unitario") or 0) if found else 0.0

# ── Stepbar ───────────────────────────────────────────────────────
def render_steps(current):
    labels = ["Nº da SC", "Propostas", "Leitura IA", "Mapa Editável", "PDF"]
    html = '<div class="steps">'
    for i, lbl in enumerate(labels):
        n = i + 1
        cls = "active" if n == current else ("done" if n < current else "")
        num = "✓" if n < current else str(n)
        html += f'<div class="step {cls}"><div class="snum">{num}</div><span>{lbl}</span></div>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────
tab_eq, tab_hist = st.tabs(["📊 Equalização", "📁 Histórico"])

# ═══════════════════════════════════════════════════════════════════
# TAB 1 — EQUALIZAÇÃO
# ═══════════════════════════════════════════════════════════════════
with tab_eq:
    render_steps(st.session_state.step)

    # ── STEP 1: Nº SC ─────────────────────────────────────────────
    if st.session_state.step == 1:
        st.markdown("### 📋 Número da Solicitação de Compra")
        sc = st.text_input(
            "Nº da SC *",
            value=st.session_state.sc_num,
            placeholder="Ex: SC-2024-0123",
            help="Usado no nome do arquivo PDF: mapa_equalizacao_[SC].html",
        )
        st.caption("Será usado no nome do arquivo gerado.")
        if st.button("Próximo: Anexar Propostas →", type="primary"):
            if not sc.strip():
                st.error("Informe o número da SC.")
            else:
                st.session_state.sc_num = sc.strip()
                st.session_state.step = 2
                st.rerun()

    # ── STEP 2: Upload ─────────────────────────────────────────────
    elif st.session_state.step == 2:
        st.markdown("### 📎 Propostas dos Fornecedores")
        st.markdown('<div class="aok">ℹ️ Envie de <strong>2 a 6 propostas</strong>. Formatos aceitos: <strong>PDF, JPG e PNG</strong>.</div>', unsafe_allow_html=True)

        uploaded = st.file_uploader(
            "Selecione os arquivos",
            type=["pdf", "jpg", "jpeg", "png"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )

        c1, c2 = st.columns([1, 5])
        with c1:
            if st.button("← Voltar"):
                st.session_state.step = 1; st.rerun()
        with c2:
            ok_upload = uploaded and len(uploaded) >= 2
            if st.button("🤖 Iniciar Leitura com IA →", type="primary", disabled=not ok_upload):
                st.session_state.uploaded_files = uploaded
                st.session_state.step = 3
                st.rerun()
            if uploaded and len(uploaded) == 1:
                st.warning("Envie pelo menos 2 propostas.")

    # ── STEP 3: Leitura IA ─────────────────────────────────────────
    elif st.session_state.step == 3:
        st.markdown("### 🤖 Leitura e Extração com IA")

        files  = st.session_state.get("uploaded_files", [])
        prog   = st.progress(0, text="Iniciando...")
        status = st.empty()
        client = get_api_client()

        PROMPT = (
            "Analise esta proposta comercial brasileira. Retorne APENAS JSON puro sem markdown.\n"
            '{"fornecedor":"nome ou null","cnpj":"cnpj ou null","contato":"nome ou null",'
            '"telefone":"tel ou null","email":"email ou null","condicoes_pagamento":"texto ou null",'
            '"prazo_atendimento":"texto ou null","itens":[{"descricao":"desc","detalhe":"detalhe ou null",'
            '"unidade":"un","quantidade":numero_ou_null,"valor_unitario":float_ou_null}]}\n'
            "REGRAS: valor_unitario como float (1200.50). Use null se não visível. Nunca invente valores."
        )

        suppliers, erros = [], 0
        for i, f in enumerate(files):
            status.info(f"📄 Lendo {i+1}/{len(files)}: **{f.name}**")
            prog.progress(i / len(files), text=f"Lendo {i+1} de {len(files)}...")
            raw  = f.read()
            b64  = base64.standard_b64encode(raw).decode()
            mt   = "application/pdf" if f.type == "application/pdf" else ("image/png" if f.type == "image/png" else "image/jpeg")
            tipo = "document" if mt == "application/pdf" else "image"
            try:
                msg = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=1500,
                    messages=[{"role":"user","content":[
                        {"type":tipo,"source":{"type":"base64","media_type":mt,"data":b64}},
                        {"type":"text","text":PROMPT},
                    ]}],
                )
                txt = re.sub(r"```json|```","", msg.content[0].text).strip()
                suppliers.append(json.loads(txt))
            except Exception as e:
                erros += 1
                st.warning(f"⚠️ Erro em {f.name}: {e}")

        prog.progress(1.0, text="Concluído!")

        if not suppliers:
            status.error("❌ Não foi possível ler nenhuma proposta.")
            if st.button("← Voltar"):
                st.session_state.step = 2; st.rerun()
        else:
            status.success(f"✅ {len(suppliers)} proposta(s) lida(s)" + (f" · {erros} com erro" if erros else ""))
            st.session_state.suppliers = suppliers
            st.session_state.prices    = {}

            master = []
            for sup in suppliers:
                for it in (sup.get("itens") or []):
                    desc = (it.get("descricao") or "").strip()
                    if desc and not any(x["descricao"].lower().strip() == desc.lower() for x in master):
                        master.append({
                            "descricao": desc,
                            "detalhe":   it.get("detalhe") or "",
                            "unidade":   it.get("unidade") or "un",
                            "quantidade": float(it.get("quantidade") or 0),
                        })
            st.session_state.master_itens = master
            pre_popular_prices()

            import time; time.sleep(0.6)
            st.session_state.step = 4
            st.rerun()

    # ── STEP 4: Mapa Editável ──────────────────────────────────────
    elif st.session_state.step == 4:
        st.markdown("### 📊 Mapa de Equalização — Edição")
        st.markdown('<div class="aok">✏️ Edite todos os campos. Menor preço por item calculado automaticamente em <strong style="color:#0d5c4a">verde</strong>.</div>', unsafe_allow_html=True)

        suppliers = st.session_state.suppliers
        master    = st.session_state.master_itens
        n         = len(suppliers)

        pre_popular_prices()

        # ── 1. Dados dos fornecedores ─────────────────────────────
        st.markdown("#### 🏢 Dados dos Fornecedores")
        for si, sup in enumerate(suppliers):
            nome_exp = sup.get("fornecedor") or f"Fornecedor {si+1}"
            with st.expander(f"**Fornecedor {si+1} — {nome_exp}**", expanded=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    suppliers[si]["fornecedor"] = st.text_input(
                        "Empresa", value=sup.get("fornecedor") or "", key=f"forn_{si}",
                        placeholder="Nome da empresa")
                    suppliers[si]["cnpj"] = st.text_input(
                        "CNPJ", value=sup.get("cnpj") or "", key=f"cnpj_{si}",
                        placeholder="00.000.000/0000-00")
                with c2:
                    suppliers[si]["contato"] = st.text_input(
                        "Contato", value=sup.get("contato") or "", key=f"cont_{si}",
                        placeholder="Nome do contato")
                    suppliers[si]["telefone"] = st.text_input(
                        "Telefone", value=sup.get("telefone") or "", key=f"tel_{si}",
                        placeholder="(00) 00000-0000")
                with c3:
                    suppliers[si]["email"] = st.text_input(
                        "E-mail", value=sup.get("email") or "", key=f"email_{si}",
                        placeholder="email@empresa.com.br")
                    suppliers[si]["condicoes_pagamento"] = st.text_input(
                        "Cond. Pagamento", value=sup.get("condicoes_pagamento") or "", key=f"pgto_{si}",
                        placeholder="Ex: 30 dias, à vista...")
                suppliers[si]["prazo_atendimento"] = st.text_input(
                    "Prazo de Atendimento", value=sup.get("prazo_atendimento") or "", key=f"prazo_{si}",
                    placeholder="Ex: 5 dias úteis")
        st.session_state.suppliers = suppliers

        # ── 2. Itens e Preços ─────────────────────────────────────
        st.markdown("#### 📋 Itens e Preços")

        if st.button("＋ Adicionar item"):
            st.session_state.master_itens.append(
                {"descricao": "Novo item", "detalhe": "", "unidade": "un", "quantidade": 0.0}
            )
            st.rerun()

        # Cabeçalho da tabela
        col_w = [0.05, 0.30, 0.18, 0.09, 0.07] + [0.22] * n
        hcols = st.columns(col_w)
        hcols[0].markdown("**⚙**")
        hcols[1].markdown("**Descrição / Detalhe**")
        hcols[2].markdown("**Detalhe**")
        hcols[3].markdown("**Qtd.**")
        hcols[4].markdown("**Un.**")
        for si, sup in enumerate(suppliers):
            nome = sup.get("fornecedor") or f"Forn. {si+1}"
            hcols[5 + si].markdown(f"**{nome[:20]}**")
        st.divider()

        to_delete = None
        master = st.session_state.master_itens

        for idx, it in enumerate(master):
            cols = st.columns(col_w)
            q = float(it.get("quantidade") or 0)

            # Coluna excluir
            with cols[0]:
                if st.button("🗑", key=f"del_{idx}", help="Excluir item"):
                    if len(master) > 1:
                        to_delete = idx
                    else:
                        st.toast("O mapa precisa ter pelo menos 1 item.", icon="⚠️")

            # Descrição
            with cols[1]:
                master[idx]["descricao"] = st.text_input(
                    "", value=it["descricao"], key=f"desc_{idx}",
                    label_visibility="collapsed")

            # Detalhe
            with cols[2]:
                master[idx]["detalhe"] = st.text_input(
                    "", value=it.get("detalhe", ""), key=f"det_{idx}",
                    placeholder="detalhe...", label_visibility="collapsed")

            # Qtd
            with cols[3]:
                new_q = st.number_input(
                    "", value=q, min_value=0.0, step=1.0,
                    key=f"qtd_{idx}", label_visibility="collapsed", format="%.2f")
                master[idx]["quantidade"] = new_q
                q = new_q

            # Un
            with cols[4]:
                master[idx]["unidade"] = st.text_input(
                    "", value=it.get("unidade", "un"), key=f"un_{idx}",
                    label_visibility="collapsed")

            # Calcula menor para este item
            m_si = menor_idx_item(idx, n)

            # Preços por fornecedor
            for si in range(n):
                with cols[5 + si]:
                    vu_key = f"vu_{si}_{idx}"
                    vu_val = st.session_state.prices.get(vu_key, 0.0)
                    new_vu = st.number_input(
                        "Vl. Unit.", value=vu_val, min_value=0.0,
                        step=0.01, format="%.4f",
                        key=vu_key, label_visibility="visible")
                    st.session_state.prices[vu_key] = new_vu

                    total = new_vu * q
                    is_menor = (si == m_si and total > 0)
                    cor   = "#0d5c4a" if is_menor else "#6b6b6b"
                    peso  = "700"    if is_menor else "400"
                    bg    = "background:#eaf7f2;border-radius:4px;padding:2px 5px;" if is_menor else ""
                    star  = "★ " if is_menor else ""
                    st.markdown(
                        f'<div style="font-family:monospace;font-size:12px;color:{cor};'
                        f'font-weight:{peso};{bg}text-align:right;margin-top:2px">'
                        f'{star}{brl(total)}</div>',
                        unsafe_allow_html=True,
                    )
            st.divider()

        # Executar deleção
        if to_delete is not None:
            st.session_state.master_itens.pop(to_delete)
            new_prices = {}
            for k, v in st.session_state.prices.items():
                parts = k.split("_")
                if len(parts) == 3 and parts[0] == "vu":
                    ri = int(parts[2])
                    if ri == to_delete:
                        continue
                    new_ri = ri if ri < to_delete else ri - 1
                    new_prices[f"vu_{parts[1]}_{new_ri}"] = v
                else:
                    new_prices[k] = v
            st.session_state.prices = new_prices
            st.rerun()

        st.session_state.master_itens = master

        # ── 3. Totais por fornecedor ──────────────────────────────
        st.markdown("#### 💰 Total por Fornecedor")
        totais = calc_totais_forn(n)
        t_val  = [t for t in totais if t > 0]
        win_si = totais.index(min(t_val)) if t_val else -1

        tcols = st.columns(n)
        for si, sup in enumerate(suppliers):
            with tcols[si]:
                is_win = si == win_si and totais[si] > 0
                bg     = "#085041" if is_win else "#0d5c4a"
                label  = "★ Menor Preço Total" if is_win else f"Fornecedor {si+1}"
                st.markdown(
                    f'<div style="background:{bg};color:white;border-radius:8px;'
                    f'padding:12px 14px;text-align:center">'
                    f'<div style="font-size:10px;opacity:.8;margin-bottom:3px">{label}</div>'
                    f'<div style="font-size:15px;font-weight:700;font-family:monospace">{brl(totais[si])}</div>'
                    f'<div style="font-size:11px;margin-top:3px">{esc(sup.get("fornecedor") or "—")}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("")
        b1, b2 = st.columns([1, 4])
        with b1:
            if st.button("← Revisar Propostas"):
                st.session_state.step = 2; st.rerun()
        with b2:
            if st.button("📄 Gerar PDF do Mapa", type="primary"):
                st.session_state.step = 5; st.rerun()

    # ── STEP 5: PDF ────────────────────────────────────────────────
    elif st.session_state.step == 5:
        st.markdown("### 📄 Gerar PDF do Mapa")

        suppliers = st.session_state.suppliers
        master    = st.session_state.master_itens
        n         = len(suppliers)
        sc_num    = st.session_state.sc_num

        totais = calc_totais_forn(n)
        t_val  = [t for t in totais if t > 0]
        win_si = totais.index(min(t_val)) if t_val else -1

        def m_idx(idx):
            return menor_idx_item(idx, n)

        # ── Pré-visualização ─────────────────────────────────────
        st.markdown(f"**SC: {sc_num}** · {datetime.datetime.now().strftime('%d/%m/%Y')}")

        forn_hds = "".join([
            f'<th colspan="2" class="{"fhw" if si==win_si and totais[si]>0 else "fh"}">'
            f'{esc(suppliers[si].get("fornecedor") or f"Forn.{si+1}")}</th>'
            for si in range(n)
        ])
        sub_hds = "".join(['<th class="sh">Vl.Unit.</th><th class="sh">Vl.Total</th>' for _ in range(n)])

        rows_html = ""
        for idx, it in enumerate(master):
            q   = float(it.get("quantidade") or 0)
            msi = m_idx(idx)
            cells = ""
            for si in range(n):
                vu    = st.session_state.prices.get(f"vu_{si}_{idx}", 0.0)
                total = vu * q
                is_m  = si == msi and total > 0
                cls   = ' class="mp"' if is_m else ''
                star  = "★ " if is_m else ""
                cells += (
                    f'<td{cls} style="text-align:right">{brl(vu) if vu>0 else "—"}</td>'
                    f'<td{cls} style="text-align:right">{star}{brl(total) if total>0 else "—"}</td>'
                )
            rows_html += (
                f'<tr><td>{esc(it["descricao"])}</td>'
                f'<td style="color:#777;font-size:11px">{esc(it.get("detalhe",""))}</td>'
                f'<td style="text-align:right">{q if q else "—"}</td>'
                f'<td style="text-align:center;color:#777">{esc(it.get("unidade",""))}</td>'
                f'{cells}</tr>'
            )

        tot_cells = "".join([
            f'<td></td><td class="{"win" if si==win_si and totais[si]>0 else ""}" '
            f'style="text-align:right">{brl(totais[si])}</td>'
            for si in range(n)
        ])

        preview = f"""
        <table class="mapa-table">
          <thead>
            <tr><th colspan="4">Insumos</th>{forn_hds}</tr>
            <tr>
              <th>Descrição</th><th>Detalhe</th>
              <th style="text-align:right">Qtd.</th>
              <th style="text-align:center">Un.</th>
              {sub_hds}
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
          <tfoot><tr><td colspan="4">TOTAL GERAL</td>{tot_cells}</tr></tfoot>
        </table>
        """

        with st.expander("👁 Pré-visualizar mapa", expanded=True):
            st.markdown(preview, unsafe_allow_html=True)

        # ── Gerar HTML do PDF ────────────────────────────────────
        html_pdf = _build_pdf_html(sc_num, suppliers, master, totais, win_si, m_idx, n)
        nome     = f"mapa_equalizacao_{sc_num.replace(' ','_')}"

        st.markdown('<div class="aok">💡 <strong>Como salvar como PDF:</strong> Baixe o arquivo, abra no Chrome ou Edge, pressione <strong>Ctrl+P</strong> → selecione <strong>Salvar como PDF</strong> → clique Salvar. O botão 🖨️ também aparece na página do arquivo.</div>', unsafe_allow_html=True)

        st.download_button(
            label="⬇️ Baixar Mapa como PDF",
            data=html_pdf.encode("utf-8"),
            file_name=f"{nome}.html",
            mime="text/html",
            type="primary",
            use_container_width=True,
        )

        # Salvar histórico
        _salvar_historico(sc_num, suppliers, totais, win_si, html_pdf)

        st.markdown("")
        b1, b2 = st.columns([1, 3])
        with b1:
            if st.button("← Voltar ao Mapa"):
                st.session_state.step = 4; st.rerun()
        with b2:
            if st.button("✅ Nova Equalização", type="primary"):
                for k in ["step","sc_num","suppliers","master_itens","uploaded_files","prices"]:
                    st.session_state.pop(k, None)
                init_state()
                st.rerun()

# ═══════════════════════════════════════════════════════════════════
# TAB 2 — HISTÓRICO
# ═══════════════════════════════════════════════════════════════════
with tab_hist:
    st.markdown("### 📁 Histórico de Equalizações")
    hist = st.session_state.get("historico", [])

    if not hist:
        st.info("Nenhuma equalização gerada ainda. Conclua o fluxo na aba Equalização para registrar aqui.")
    else:
        st.markdown(f"**{len(hist)} mapa(s) gerado(s) nesta sessão**")
        st.markdown("")
        for i, h in enumerate(reversed(hist)):
            with st.container():
                c1, c2, c3, c4 = st.columns([1.2, 2, 2, 1])
                with c1:
                    st.markdown(f"**🗂 SC: {h['sc_num']}**")
                    st.caption(h["data"])
                with c2:
                    st.markdown(f"**{h['n_forn']} fornecedor(es)**")
                    st.caption(" · ".join(h["fornecedores"]))
                with c3:
                    st.markdown(f"**Menor total:** {h['menor_total']}")
                    st.caption(f"Vencedor: {h['vencedor']}")
                with c4:
                    st.download_button(
                        "⬇️ PDF",
                        data=h["html"].encode("utf-8"),
                        file_name=f"mapa_equalizacao_{h['sc_num']}.html",
                        mime="text/html",
                        key=f"dl_h_{i}",
                    )
                st.divider()

# ═══════════════════════════════════════════════════════════════════
# FUNÇÕES DE GERAÇÃO DE PDF
# ═══════════════════════════════════════════════════════════════════

def _salvar_historico(sc_num, suppliers, totais_forn, win_idx, html_pdf):
    hist = st.session_state.get("historico", [])
    if any(h["sc_num"] == sc_num for h in hist):
        return
    t_val    = [t for t in totais_forn if t > 0]
    vencedor = suppliers[win_idx].get("fornecedor", "—") if win_idx >= 0 else "—"
    menor    = brl(min(t_val)) if t_val else "—"
    hist.append({
        "sc_num":      sc_num,
        "data":        datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "n_forn":      len(suppliers),
        "fornecedores":[s.get("fornecedor") or f"Forn.{i+1}" for i, s in enumerate(suppliers)],
        "vencedor":    vencedor,
        "menor_total": menor,
        "html":        html_pdf,
    })
    st.session_state.historico = hist


def _build_pdf_html(sc_num, suppliers, master, totais_forn, win_idx, menor_idx_fn, n):
    """Gera o HTML completo do PDF para download."""

    def _forn_hd(si):
        bg    = "#085041" if si == win_idx and totais_forn[si] > 0 else "#1a7a62"
        nome  = esc(suppliers[si].get("fornecedor") or f"Fornecedor {si+1}")
        cnpj  = suppliers[si].get("cnpj") or ""
        cnpj_div = f'<div style="font-size:9px;opacity:.8">{esc(cnpj)}</div>' if cnpj else ""
        return (
            f'<th colspan="2" style="background:{bg};color:#fff;padding:7px 9px;'
            f'font-size:10px;text-align:center;border-right:1px solid rgba(255,255,255,.2)">'
            f'<div style="font-weight:700">{nome}</div>{cnpj_div}</th>'
        )
    forn_hds = "".join([_forn_hd(si) for si in range(n)])

    sub_hds = "".join([
        '<th style="background:#0f6e56;color:#fff;padding:4px 7px;font-size:9px;text-align:right">Preço Unit.</th>'
        '<th style="background:#0f6e56;color:#fff;padding:4px 7px;font-size:9px;text-align:right">Preço Total</th>'
        for _ in range(n)
    ])

    rows = ""
    for idx, it in enumerate(master):
        q   = float(it.get("quantidade") or 0)
        msi = menor_idx_fn(idx)
        cells = ""
        for si in range(n):
            vu    = st.session_state.prices.get(f"vu_{si}_{idx}", 0.0)
            total = vu * q
            is_m  = si == msi and total > 0
            bg    = "background:#eaf7f2;font-weight:700;color:#0d5c4a;" if is_m else ""
            star  = "★ " if is_m else ""
            cells += (
                f'<td style="{bg}text-align:right;font-size:10px;padding:5px 7px;border-right:1px solid #eee">'
                f'{brl(vu) if vu>0 else "—"}</td>'
                f'<td style="{bg}text-align:right;font-size:10px;padding:5px 7px;border-right:1px solid #eee">'
                f'{star}{brl(total) if total>0 else "—"}</td>'
            )
        rows += (
            f'<tr style="border-bottom:1px solid #eee">'
            f'<td style="font-size:10px;padding:5px 7px">{esc(it["descricao"])}</td>'
            f'<td style="font-size:9px;color:#777;padding:5px 7px">{esc(it.get("detalhe",""))}</td>'
            f'<td style="font-size:10px;text-align:right;padding:5px 7px;font-family:monospace">{q if q else ""}</td>'
            f'<td style="font-size:10px;text-align:center;padding:5px 7px;color:#777">{esc(it.get("unidade",""))}</td>'
            f'{cells}</tr>'
        )

    tot_cells = "".join([
        f'<td></td><td style="text-align:right;padding:8px 7px;font-weight:700;color:#fff;'
        f'{"background:#085041" if si==win_idx and totais_forn[si]>0 else ""}">'
        f'{brl(totais_forn[si])}</td>'
        for si in range(n)
    ])

    finfos = "".join([
        f'<div style="background:#f5f5f3;border:1px solid #ddd;border-radius:5px;padding:9px 11px;font-size:9.5px">'
        f'<div style="font-weight:700;color:#0d5c4a;margin-bottom:4px">'
        f'Fornecedor {si+1}{" ★ Menor Preço Total" if si==win_idx and totais_forn[si]>0 else ""}</div>'
        f'<div><b>Empresa:</b> {esc(suppliers[si].get("fornecedor","—"))}</div>'
        f'<div><b>CNPJ:</b> {esc(suppliers[si].get("cnpj","—"))}</div>'
        f'<div><b>Contato:</b> {esc(suppliers[si].get("contato","—"))}</div>'
        f'<div><b>Telefone:</b> {esc(suppliers[si].get("telefone","—"))}</div>'
        f'<div><b>E-mail:</b> {esc(suppliers[si].get("email","—"))}</div>'
        f'{"<div><b>Pgto:</b> "+esc(suppliers[si].get("condicoes_pagamento",""))+"</div>" if suppliers[si].get("condicoes_pagamento") else ""}'
        f'{"<div><b>Prazo:</b> "+esc(suppliers[si].get("prazo_atendimento",""))+"</div>" if suppliers[si].get("prazo_atendimento") else ""}'
        f'</div>'
        for si in range(n)
    ])

    data_str = datetime.datetime.now().strftime("%d/%m/%Y")
    hora_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8">
<title>mapa_equalizacao_{esc(sc_num)}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Arial,sans-serif;font-size:11px;color:#1a1a1a;padding:18px}}
@media print{{
  @page{{size:A4 landscape;margin:10mm}}
  body{{padding:0}}
  .np{{display:none!important}}
}}
table{{width:100%;border-collapse:collapse}}
.top{{display:flex;justify-content:space-between;align-items:flex-start;
  margin-bottom:14px;padding-bottom:10px;border-bottom:2px solid #0d5c4a}}
.fg{{display:grid;grid-template-columns:repeat({n},1fr);gap:8px;margin-bottom:14px}}
.pbtn{{position:fixed;bottom:22px;right:22px;background:#c9a227;color:#fff;border:none;
  padding:12px 22px;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer;
  box-shadow:0 4px 16px rgba(0,0,0,.25);z-index:999}}
.pbtn:hover{{background:#b8911e}}
</style>
</head><body>
<button class="np pbtn" onclick="window.print()">🖨️ Imprimir / Salvar PDF</button>
<div class="top">
  <div>
    <div style="font-size:17px;font-weight:700;color:#0d5c4a">Wert<span style="color:#c9a227">.</span></div>
    <div style="font-size:13px;font-weight:700">EQUALIZAÇÃO DE PROPOSTAS · FM-030</div>
  </div>
  <div style="text-align:right;font-size:10px;color:#555">
    <div style="font-weight:700;font-size:12px">SC: {esc(sc_num)}</div>
    <div>Rev.00 · {data_str}</div>
  </div>
</div>
<div class="fg">{finfos}</div>
<table>
  <thead>
    <tr>
      <th rowspan="2" style="background:#0d5c4a;color:#fff;padding:7px 8px;text-align:left">Descrição</th>
      <th rowspan="2" style="background:#0d5c4a;color:#fff;padding:7px 8px">Detalhe</th>
      <th rowspan="2" style="background:#0d5c4a;color:#fff;padding:7px 8px;text-align:right">Qtd.</th>
      <th rowspan="2" style="background:#0d5c4a;color:#fff;padding:7px 8px;text-align:center">Un.</th>
      {forn_hds}
    </tr>
    <tr>{sub_hds}</tr>
  </thead>
  <tbody>{rows}</tbody>
  <tfoot>
    <tr style="background:#0d5c4a;color:#fff">
      <td colspan="4" style="padding:8px;font-weight:700">TOTAL GERAL</td>
      {tot_cells}
    </tr>
  </tfoot>
</table>
<div style="margin-top:14px;display:flex;justify-content:space-between;
  font-size:9px;color:#bbb;border-top:1px solid #eee;padding-top:7px">
  <span>Agente FM-030 · Allwert · {hora_str}</span>
  <span>mapa_equalizacao_{esc(sc_num)}.pdf</span>
</div>
</body></html>"""
