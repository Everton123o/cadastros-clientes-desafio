const { useEffect, useMemo, useState } = React;

const API_BASE = window.location.port === "5173" ? "http://localhost:8000" : "";

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let msg = `Erro HTTP ${res.status}`;
    try {
      const err = await res.json();
      if (err.detail) msg = err.detail;
    } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
}

function App() {
  const [tab, setTab] = useState("marcar");
  const [operador, setOperador] = useState("equipe");
  const [sample, setSample] = useState({ total: 0, rotulados: 0, vizinhancas: [], registros: [] });
  const [onlyPending, setOnlyPending] = useState(false);
  const [selectedHood, setSelectedHood] = useState(null);
  const [draftLabels, setDraftLabels] = useState({});
  const [search, setSearch] = useState("");
  const [limiar, setLimiar] = useState(25);
  const [evalData, setEvalData] = useState(null);
  const [pipelineData, setPipelineData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState(null);

  const loadSample = async () => {
    try {
      const data = await apiFetch("/api/gabarito/amostra");
      setSample(data);
      if (data.vizinhancas?.length && selectedHood === null) {
        setSelectedHood(data.vizinhancas[0]);
      }
    } catch (e) {
      setFeedback({ type: "error", text: e.message });
    }
  };

  const loadEvaluation = async (t = limiar) => {
    setLoading(true);
    try {
      const data = await apiFetch(`/api/gabarito/avaliar?limiar=${t}`);
      setEvalData(data);
    } catch (e) {
      setFeedback({ type: "error", text: e.message });
    } finally {
      setLoading(false);
    }
  };

  const loadPipelineSummary = async () => {
    try {
      const data = await apiFetch("/api/pipeline/resumo");
      setPipelineData(data.execucao);
    } catch (e) {
      setFeedback({ type: "error", text: e.message });
    }
  };

  useEffect(() => {
    loadSample();
    loadEvaluation(25);
    loadPipelineSummary();
  }, []);

  const hoods = useMemo(() => {
    const all = sample.vizinhancas || [];
    if (!onlyPending) return all;
    return all.filter((h) =>
      sample.registros.some((r) => r.vizinhanca === h && !r.pessoa)
    );
  }, [sample, onlyPending]);

  useEffect(() => {
    if (hoods.length && !hoods.includes(selectedHood)) {
      setSelectedHood(hoods[0]);
    }
  }, [hoods, selectedHood]);

  const currentHoodRecords = useMemo(() => {
    return sample.registros.filter((r) => r.vizinhanca === selectedHood);
  }, [sample, selectedHood]);

  useEffect(() => {
    const next = {};
    for (const r of currentHoodRecords) {
      next[r.id_registro] = r.pessoa || "";
    }
    setDraftLabels(next);
  }, [currentHoodRecords]);

  const handleSaveHood = async (customMap = null) => {
    if (!operador.trim()) {
      setFeedback({ type: "error", text: "Informe o nome do operador no topo da página." });
      return;
    }
    setLoading(true);
    setFeedback(null);
    try {
      await apiFetch("/api/gabarito/rotulos", {
        method: "PUT",
        body: JSON.stringify({
          operador: operador.trim(),
          rotulos: customMap || draftLabels,
        }),
      });
      await loadSample();
      await loadEvaluation(limiar);
      setFeedback({ type: "ok", text: `Vizinhança #${selectedHood} salva com sucesso.` });
    } catch (e) {
      setFeedback({ type: "error", text: e.message });
    } finally {
      setLoading(false);
    }
  };

  const handleMarkSamePerson = () => {
    const map = {};
    for (const r of currentHoodRecords) {
      map[r.id_registro] = `V${selectedHood}`;
    }
    setDraftLabels(map);
    handleSaveHood(map);
  };

  const handleMarkDistinctPeople = () => {
    const map = {};
    for (const r of currentHoodRecords) {
      map[r.id_registro] = `R${r.id_registro}`;
    }
    setDraftLabels(map);
    handleSaveHood(map);
  };

  const handleRunPipeline = async () => {
    setLoading(true);
    setFeedback(null);
    try {
      await apiFetch("/api/pipeline/rodar", {
        method: "POST",
        body: JSON.stringify({ limiar: Number(limiar) }),
      });
      await loadPipelineSummary();
      await loadEvaluation(limiar);
      setFeedback({ type: "ok", text: `Pipeline executado com limiar = ${limiar} pontos.` });
    } catch (e) {
      setFeedback({ type: "error", text: e.message });
    } finally {
      setLoading(false);
    }
  };

  const filteredSample = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return sample.registros;
    return sample.registros.filter(
      (r) =>
        String(r.id_registro).includes(q) ||
        (r.nome || "").toLowerCase().includes(q) ||
        (r.cpf || "").toLowerCase().includes(q) ||
        (r.cidade || "").toLowerCase().includes(q) ||
        (r.pessoa || "").toLowerCase().includes(q)
    );
  }, [sample.registros, search]);

  const pctDone = sample.total ? Math.round((sample.rotulados / sample.total) * 100) : 0;

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top Navbar */}
      <header className="bg-slate-900 text-white border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
              <span className="text-xs uppercase tracking-wider text-slate-400 font-semibold">
                FastAPI + React + Tailwind + SQLAlchemy
              </span>
            </div>
            <h1 className="text-xl font-bold tracking-tight mt-0.5">
              Deduplicação de Cadastros de Clientes
            </h1>
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2 bg-slate-800 px-3 py-1.5 rounded-lg border border-slate-700">
              <label className="text-xs text-slate-300 font-medium">Operador:</label>
              <input
                type="text"
                value={operador}
                onChange={(e) => setOperador(e.target.value)}
                placeholder="Seu nome"
                className="bg-transparent text-sm text-white focus:outline-none w-32 border-b border-slate-600 focus:border-emerald-400"
              />
            </div>

            <div className="bg-slate-800 px-3 py-1.5 rounded-lg border border-slate-700">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="text-slate-300">Gabarito marcado</span>
                <span className="font-bold text-emerald-400">
                  {sample.rotulados} / {sample.total} ({pctDone}%)
                </span>
              </div>
              <div className="w-40 bg-slate-700 h-1.5 rounded-full mt-1 overflow-hidden">
                <div
                  className="bg-emerald-400 h-full transition-all"
                  style={{ width: `${pctDone}%` }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex gap-2 border-t border-slate-800 pt-2">
          {[
            { id: "marcar", label: "1. Marcar Gabarito (Cego)" },
            { id: "amostra", label: "2. Amostra Estratificada (100)" },
            { id: "metricas", label: "3. Métricas (Precisão & Revocação)" },
            { id: "pipeline", label: "4. Pipeline & Blocking (3.000)" },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors ${
                tab === t.id
                  ? "bg-slate-50 text-slate-900 font-semibold"
                  : "text-slate-300 hover:text-white hover:bg-slate-800"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 space-y-6">
        {feedback && (
          <div
            className={`px-4 py-3 rounded-lg text-sm font-medium flex items-center justify-between ${
              feedback.type === "error"
                ? "bg-red-50 text-red-800 border border-red-200"
                : "bg-emerald-50 text-emerald-800 border border-emerald-200"
            }`}
          >
            <span>{feedback.text}</span>
            <button onClick={() => setFeedback(null)} className="text-xs underline ml-4">
              fechar
            </button>
          </div>
        )}

        {/* TAB 1: MARCAR GABARITO */}
        {tab === "marcar" && (
          <div className="space-y-4">
            <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                <div>
                  <h2 className="text-base font-bold text-slate-800">
                    Marcação Cega por Vizinhança
                  </h2>
                  <p className="text-sm text-slate-600 mt-0.5">
                    Registros com o <strong>mesmo rótulo</strong> na coluna{" "}
                    <code className="bg-slate-100 px-1.5 py-0.5 rounded text-xs">pessoa</code>{" "}
                    indicam a mesma pessoa real. Pontuações e sugestões do sistema ficam ocultas
                    para não enviesar o gabarito.
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={onlyPending}
                      onChange={(e) => setOnlyPending(e.target.checked)}
                      className="rounded border-slate-300"
                    />
                    Somente pendentes
                  </label>

                  <select
                    value={selectedHood ?? ""}
                    onChange={(e) => setSelectedHood(Number(e.target.value))}
                    className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm bg-white font-medium"
                  >
                    {hoods.map((h) => (
                      <option key={h} value={h}>
                        Vizinhança #{h}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Records Table */}
              <div className="mt-4 overflow-x-auto border border-slate-200 rounded-lg">
                <table className="w-full text-sm text-left">
                  <thead className="bg-slate-100 text-slate-700 uppercase text-xs font-semibold">
                    <tr>
                      <th className="px-3 py-2.5">ID</th>
                      <th className="px-3 py-2.5">Origem</th>
                      <th className="px-3 py-2.5">Nome</th>
                      <th className="px-3 py-2.5">CPF</th>
                      <th className="px-3 py-2.5">Nascimento</th>
                      <th className="px-3 py-2.5">Telefone</th>
                      <th className="px-3 py-2.5">E-mail</th>
                      <th className="px-3 py-2.5">Cidade/UF</th>
                      <th className="px-3 py-2.5 w-44">Rótulo (Pessoa)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {currentHoodRecords.map((r) => (
                      <tr key={r.id_registro} className="hover:bg-slate-50">
                        <td className="px-3 py-2.5 font-mono text-xs font-semibold">
                          #{r.id_registro}
                        </td>
                        <td className="px-3 py-2.5">
                          <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700">
                            {r.sistema_origem}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 font-medium text-slate-900">{r.nome}</td>
                        <td className="px-3 py-2.5 font-mono text-xs text-slate-700">
                          {r.cpf || <span className="text-slate-400">ausente</span>}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-xs text-slate-700">
                          {r.data_nascimento || <span className="text-slate-400">ausente</span>}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-xs text-slate-700">
                          {r.telefone}
                        </td>
                        <td className="px-3 py-2.5 text-xs text-slate-700">
                          {r.email || <span className="text-slate-400">ausente</span>}
                        </td>
                        <td className="px-3 py-2.5 text-xs text-slate-700">
                          {r.cidade} / {r.uf}
                        </td>
                        <td className="px-3 py-2.5">
                          <input
                            type="text"
                            value={draftLabels[r.id_registro] ?? ""}
                            onChange={(e) =>
                              setDraftLabels({
                                ...draftLabels,
                                [r.id_registro]: e.target.value,
                              })
                            }
                            placeholder="Ex: V1 ou R123"
                            className="w-full border border-slate-300 rounded-md px-2.5 py-1 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-slate-900"
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Action Buttons */}
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => handleSaveHood()}
                    disabled={loading}
                    className="bg-slate-900 hover:bg-slate-800 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
                  >
                    Salvar Rótulos
                  </button>
                  <button
                    onClick={handleMarkSamePerson}
                    disabled={loading}
                    className="bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium px-3.5 py-2 rounded-lg transition-colors"
                  >
                    Todos são a mesma pessoa (V{selectedHood})
                  </button>
                  <button
                    onClick={handleMarkDistinctPeople}
                    disabled={loading}
                    className="bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium px-3.5 py-2 rounded-lg transition-colors"
                  >
                    Cada registro é uma pessoa diferente
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      const idx = hoods.indexOf(selectedHood);
                      if (idx > 0) setSelectedHood(hoods[idx - 1]);
                    }}
                    className="px-3 py-1.5 text-xs font-medium border border-slate-300 rounded-lg hover:bg-slate-100"
                  >
                    ← Anterior
                  </button>
                  <button
                    onClick={() => {
                      const idx = hoods.indexOf(selectedHood);
                      if (idx >= 0 && idx < hoods.length - 1) setSelectedHood(hoods[idx + 1]);
                    }}
                    className="px-3 py-1.5 text-xs font-medium border border-slate-300 rounded-lg hover:bg-slate-100"
                  >
                    Próxima →
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: AMOSTRA INTEIRA */}
        {tab === "amostra" && (
          <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <h2 className="text-base font-bold text-slate-800">
                  Amostra Estratificada (100 registros em 49 vizinhanças)
                </h2>
                <p className="text-xs text-slate-500">
                  Consulte todos os registros sorteados e seus respectivos rótulos no gabarito.
                </p>
              </div>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filtrar por nome, CPF, cidade ou rótulo..."
                className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm w-full sm:w-80"
              />
            </div>

            <div className="overflow-x-auto border border-slate-200 rounded-lg max-h-[600px]">
              <table className="w-full text-sm text-left">
                <thead className="bg-slate-100 text-slate-700 uppercase text-xs font-semibold sticky top-0">
                  <tr>
                    <th className="px-3 py-2">Viz.</th>
                    <th className="px-3 py-2">ID</th>
                    <th className="px-3 py-2">Origem</th>
                    <th className="px-3 py-2">Nome</th>
                    <th className="px-3 py-2">CPF</th>
                    <th className="px-3 py-2">Nascimento</th>
                    <th className="px-3 py-2">Telefone</th>
                    <th className="px-3 py-2">E-mail</th>
                    <th className="px-3 py-2">Cidade</th>
                    <th className="px-3 py-2">Pessoa (Gabarito)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {filteredSample.map((r) => (
                    <tr key={r.id_registro} className="hover:bg-slate-50">
                      <td className="px-3 py-2 font-mono text-xs text-slate-500">
                        #{r.vizinhanca}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs font-semibold">
                        {r.id_registro}
                      </td>
                      <td className="px-3 py-2 text-xs">{r.sistema_origem}</td>
                      <td className="px-3 py-2 font-medium">{r.nome}</td>
                      <td className="px-3 py-2 font-mono text-xs">{r.cpf || "—"}</td>
                      <td className="px-3 py-2 font-mono text-xs">{r.data_nascimento || "—"}</td>
                      <td className="px-3 py-2 font-mono text-xs">{r.telefone}</td>
                      <td className="px-3 py-2 text-xs">{r.email || "—"}</td>
                      <td className="px-3 py-2 text-xs">
                        {r.cidade}/{r.uf}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs font-bold text-emerald-700">
                        {r.pessoa || <span className="text-amber-600">pendente</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 3: MÉTRICAS */}
        {tab === "metricas" && evalData && (
          <div className="space-y-6">
            {/* Threshold Selector & KPI Cards */}
            <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-4 border-b border-slate-100">
                <div>
                  <h2 className="text-base font-bold text-slate-800">
                    Avaliação contra o Gabarito ({evalData.rotulados} registros,{" "}
                    {evalData.pessoas_distintas_gabarito} pessoas únicas)
                  </h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Política da equipe: priorizar precisão (zero falsos positivos — é melhor deixar
                    duplicatas passarem do que fundir pessoas diferentes).
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <label className="text-sm font-medium text-slate-700">
                    Limiar (pontos):
                  </label>
                  <select
                    value={limiar}
                    onChange={(e) => {
                      const val = Number(e.target.value);
                      setLimiar(val);
                      loadEvaluation(val);
                    }}
                    className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm font-semibold bg-white"
                  >
                    {evalData.varredura_limiares.map((row) => (
                      <option key={row.limiar_pontos} value={row.limiar_pontos}>
                        {row.limiar_pontos} pts
                        {row.limiar_pontos === 25 ? " (Recomendado - 50% conf.)" : ""}
                        {row.limiar_pontos === 35 ? " (Conservador - 80,7% conf.)" : ""}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 mt-4">
                <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
                  <div className="text-xs text-slate-500">Revocação do Blocking</div>
                  <div className="text-xl font-bold text-slate-900 mt-1">
                    {(evalData.blocking.revocacao_blocking * 100).toFixed(1)}%
                  </div>
                  <div className="text-[11px] text-slate-500">
                    {evalData.blocking.gerados_pelo_blocking}/{evalData.blocking.pares_verdadeiros}{" "}
                    pares gerados
                  </div>
                </div>

                <div className="p-3.5 rounded-lg bg-emerald-50 border border-emerald-200">
                  <div className="text-xs text-emerald-700 font-medium">Precisão</div>
                  <div className="text-xl font-bold text-emerald-900 mt-1">
                    {(evalData.metricas_limiar.precisao * 100).toFixed(2)}%
                  </div>
                  <div className="text-[11px] text-emerald-700">
                    VP / (VP + FP)
                  </div>
                </div>

                <div className="p-3.5 rounded-lg bg-blue-50 border border-blue-200">
                  <div className="text-xs text-blue-700 font-medium">Revocação</div>
                  <div className="text-xl font-bold text-blue-900 mt-1">
                    {(evalData.metricas_limiar.revocacao * 100).toFixed(2)}%
                  </div>
                  <div className="text-[11px] text-blue-700">
                    VP / (VP + FN)
                  </div>
                </div>

                <div className="p-3.5 rounded-lg bg-indigo-50 border border-indigo-200">
                  <div className="text-xs text-indigo-700 font-medium">F0.5 (foco Precisão)</div>
                  <div className="text-xl font-bold text-indigo-900 mt-1">
                    {(evalData.metricas_limiar.f0_5 * 100).toFixed(2)}%
                  </div>
                  <div className="text-[11px] text-indigo-700">
                    F1: {(evalData.metricas_limiar.f1 * 100).toFixed(2)}%
                  </div>
                </div>

                <div className="p-3.5 rounded-lg bg-red-50 border border-red-200">
                  <div className="text-xs text-red-700 font-medium">Falsos Positivos (FP)</div>
                  <div className="text-xl font-bold text-red-900 mt-1">
                    {evalData.metricas_limiar.FP}
                  </div>
                  <div className="text-[11px] text-red-700">Pessoas distintas fundidas</div>
                </div>

                <div className="p-3.5 rounded-lg bg-amber-50 border border-amber-200">
                  <div className="text-xs text-amber-700 font-medium">Falsos Negativos (FN)</div>
                  <div className="text-xl font-bold text-amber-900 mt-1">
                    {evalData.metricas_limiar.FN}
                  </div>
                  <div className="text-[11px] text-amber-700">Duplicatas que passaram</div>
                </div>
              </div>
            </div>

            {/* Sweep Table */}
            <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200">
              <h3 className="text-sm font-bold text-slate-800 mb-3">
                Efeito do Limiar em Falsos Positivos (FP) e Falsos Negativos (FN)
              </h3>
              <div className="overflow-x-auto border border-slate-200 rounded-lg">
                <table className="w-full text-sm text-left">
                  <thead className="bg-slate-100 text-slate-700 uppercase text-xs font-semibold">
                    <tr>
                      <th className="px-3 py-2">Limiar (pts)</th>
                      <th className="px-3 py-2">VP</th>
                      <th className="px-3 py-2">FP</th>
                      <th className="px-3 py-2">FN</th>
                      <th className="px-3 py-2">VN</th>
                      <th className="px-3 py-2">Precisão</th>
                      <th className="px-3 py-2">Revocação</th>
                      <th className="px-3 py-2">F1</th>
                      <th className="px-3 py-2">F0.5</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {evalData.varredura_limiares.map((r) => {
                      const active = r.limiar_pontos === limiar;
                      return (
                        <tr
                          key={r.limiar_pontos}
                          onClick={() => {
                            setLimiar(r.limiar_pontos);
                            loadEvaluation(r.limiar_pontos);
                          }}
                          className={`cursor-pointer ${
                            active ? "bg-emerald-50 font-semibold" : "hover:bg-slate-50"
                          }`}
                        >
                          <td className="px-3 py-2 font-mono">
                            {r.limiar_pontos}
                            {r.limiar_pontos === 25 && (
                              <span className="ml-2 px-1.5 py-0.5 text-[10px] rounded bg-emerald-600 text-white">
                                padrão
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 font-mono">{r.VP}</td>
                          <td className="px-3 py-2 font-mono text-red-700">{r.FP}</td>
                          <td className="px-3 py-2 font-mono text-amber-700">{r.FN}</td>
                          <td className="px-3 py-2 font-mono text-slate-500">{r.VN}</td>
                          <td className="px-3 py-2 font-mono">
                            {(r.precisao * 100).toFixed(2)}%
                          </td>
                          <td className="px-3 py-2 font-mono">
                            {(r.revocacao * 100).toFixed(2)}%
                          </td>
                          <td className="px-3 py-2 font-mono">{(r.f1 * 100).toFixed(2)}%</td>
                          <td className="px-3 py-2 font-mono">{(r.f0_5 * 100).toFixed(2)}%</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* FP / FN Details */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200">
                <h3 className="text-sm font-bold text-red-800 mb-2">
                  Falsos Positivos no Limiar {limiar} ({evalData.fp_detalhes.length})
                </h3>
                {evalData.fp_detalhes.length === 0 ? (
                  <p className="text-xs text-slate-500">
                    Nenhum falso positivo neste limiar (Precisão = 100%).
                  </p>
                ) : (
                  <div className="space-y-2">
                    {evalData.fp_detalhes.map((p) => (
                      <div
                        key={`${p.id_a}-${p.id_b}`}
                        className="p-3 rounded-lg bg-red-50 border border-red-200 text-xs space-y-1"
                      >
                        <div className="font-bold text-red-900">
                          #{p.id_a} × #{p.id_b} — {p.pontos} pts ({p.blocos})
                        </div>
                        <div>
                          A: {p.registro_a.nome} | CPF: {p.registro_a.cpf || "—"} | Tel:{" "}
                          {p.registro_a.telefone}
                        </div>
                        <div>
                          B: {p.registro_b.nome} | CPF: {p.registro_b.cpf || "—"} | Tel:{" "}
                          {p.registro_b.telefone}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200">
                <h3 className="text-sm font-bold text-amber-800 mb-2">
                  Falsos Negativos no Limiar {limiar} ({evalData.fn_detalhes.length})
                </h3>
                <div className="space-y-2 max-h-80 overflow-y-auto">
                  {evalData.fn_detalhes.map((p) => (
                    <div
                      key={`${p.id_a}-${p.id_b}`}
                      className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-xs space-y-1"
                    >
                      <div className="font-bold text-amber-900">
                        #{p.id_a} × #{p.id_b} — {p.pontos} pts (abaixo de {limiar} pts)
                      </div>
                      <div>
                        A ({p.registro_a.sistema_origem}): {p.registro_a.nome} | CPF:{" "}
                        {p.registro_a.cpf || "—"} | Tel: {p.registro_a.telefone}
                      </div>
                      <div>
                        B ({p.registro_b.sistema_origem}): {p.registro_b.nome} | CPF:{" "}
                        {p.registro_b.cpf || "—"} | Tel: {p.registro_b.telefone}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: PIPELINE & BLOCKING */}
        {tab === "pipeline" && (
          <div className="space-y-6">
            <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                  <h2 className="text-base font-bold text-slate-800">
                    Execução nos 3.000 Registros Completos
                  </h2>
                  <p className="text-xs text-slate-500">
                    Dispare o pipeline completo (normalização, blocking multichave, pontuação e
                    clustering) e salve no banco SQLAlchemy.
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <input
                    type="number"
                    value={limiar}
                    onChange={(e) => setLimiar(Number(e.target.value))}
                    className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm w-24 font-mono"
                  />
                  <button
                    onClick={handleRunPipeline}
                    disabled={loading}
                    className="bg-slate-900 hover:bg-slate-800 text-white text-sm font-semibold px-4 py-2 rounded-lg"
                  >
                    Rodar Pipeline Agora
                  </button>
                </div>
              </div>

              {pipelineData && (
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 mt-5">
                  <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
                    <div className="text-xs text-slate-500">Pares Possíveis</div>
                    <div className="text-lg font-bold text-slate-900 mt-1">
                      {pipelineData.estatisticas.pares_possiveis?.toLocaleString("pt-BR")}
                    </div>
                  </div>
                  <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
                    <div className="text-xs text-slate-500">Pares Candidatos</div>
                    <div className="text-lg font-bold text-slate-900 mt-1">
                      {pipelineData.estatisticas.pares_candidatos?.toLocaleString("pt-BR")}
                    </div>
                  </div>
                  <div className="p-3.5 rounded-lg bg-emerald-50 border border-emerald-200">
                    <div className="text-xs text-emerald-700">Redução do Blocking</div>
                    <div className="text-lg font-bold text-emerald-900 mt-1">
                      {pipelineData.estatisticas.reducao_pct}%
                    </div>
                  </div>
                  <div className="p-3.5 rounded-lg bg-blue-50 border border-blue-200">
                    <div className="text-xs text-blue-700">Grupos Formados (2+)</div>
                    <div className="text-lg font-bold text-blue-900 mt-1">
                      {pipelineData.estatisticas.grupos_com_2_ou_mais}
                    </div>
                  </div>
                  <div className="p-3.5 rounded-lg bg-indigo-50 border border-indigo-200">
                    <div className="text-xs text-indigo-700">Registros Agrupados</div>
                    <div className="text-lg font-bold text-indigo-900 mt-1">
                      {pipelineData.estatisticas.registros_em_grupos}
                    </div>
                  </div>
                  <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
                    <div className="text-xs text-slate-500">Clientes Estimados</div>
                    <div className="text-lg font-bold text-slate-900 mt-1">
                      {pipelineData.estatisticas.pessoas_estimadas}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);

