"""
Panel de solo lectura para ver el estado del Knowledge State de Praxis
(Capa 1 Decision Ledger, Capa 2 Artefactos, Capa 4 Gobernanza) sin tener que
consultar Postgres a mano. Lee en vivo en cada request -- no cachea nada, asi
que siempre refleja lo que haya en la base en ese momento.

GET /admin -- pagina HTML. No requiere autenticacion: pensado para uso local
de desarrollo/demo, no para exponer en produccion tal cual.
"""
import json

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from psycopg2.extras import RealDictCursor

from praxis.db import get_connection

router = APIRouter()

_ARTIFACT_STATUS_COLOR = {
    "CHAMPION": "#1a7f37",
    "CHALLENGER": "#9a6700",
    "CANDIDATE": "#57606a",
    "TRAINING": "#57606a",
    "RETIRED": "#cf222e",
}

_DECISION_STATUS_COLOR = {
    "PENDING_RESULT": "#0969da",
    "RESULT_RECEIVED": "#9a6700",
    "PROCESSED_FOR_LEARNING": "#1a7f37",
    "ABANDONED": "#cf222e",
}

MAX_DECISIONS = 30
MAX_CANDIDATES_PER_DECISION = 5


def _badge(texto, color):
    return f'<span style="background:{color}22;color:{color};border:1px solid {color}55;border-radius:10px;padding:2px 9px;font-size:12px;font-weight:600;">{texto}</span>'


def _fmt_dt(dt):
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "-"


def _fmt_num(x, nd=2):
    return f"{x:,.{nd}f}" if x is not None else "-"


def _fetch_manifest(cur):
    cur.execute("SELECT ambiente, champion_id, champion_desde, champion_por, challenger_id, challenger_desde FROM production_manifest ORDER BY ambiente")
    return cur.fetchall()


def _fetch_artifacts(cur):
    cur.execute(
        """
        SELECT artifact_id, tipo, status, descripcion, metricas, created_at, promoted_at, retired_at
        FROM artifacts ORDER BY tipo, status, created_at
        """
    )
    return cur.fetchall()


def _fetch_decisions(cur):
    cur.execute(
        f"""
        SELECT decision_id, status, timestamp_decision, timestamp_resultado, timestamp_procesado,
               vector_estado -> 'recurso' ->> 'truck_id' AS truck_id,
               vector_estado -> 'recurso' ->> 'zone_actual_code' AS zone_actual_code,
               vector_estado -> 'recurso' ->> 'tipo_equipo' AS tipo_equipo,
               vector_estado -> 'restricciones_y_objetivos' ->> 'destino_final_code' AS destino_final_code,
               vector_estado -> 'restricciones_y_objetivos' ->> 'politica_de_decision' AS politica_de_decision
        FROM decisions
        ORDER BY timestamp_decision DESC
        LIMIT {MAX_DECISIONS}
        """
    )
    return cur.fetchall()


def _fetch_candidates(cur, decision_ids):
    if not decision_ids:
        return {}
    cur.execute(
        """
        SELECT decision_id, route_id, rank_posicion, fue_elegido, puntaje, profit_estimado
        FROM decision_candidates
        WHERE decision_id = ANY(%s)
        ORDER BY decision_id, rank_posicion
        """,
        (decision_ids,),
    )
    by_decision = {}
    for row in cur.fetchall():
        by_decision.setdefault(row["decision_id"], []).append(row)
    return by_decision


def _fetch_results(cur, decision_ids):
    if not decision_ids:
        return {}
    cur.execute(
        """
        SELECT decision_id, profit_apl_real, rpm_efectivo, pct_deadhead, total_millas, timestamp_resultado
        FROM decision_results
        WHERE decision_id = ANY(%s)
        """,
        (decision_ids,),
    )
    return {row["decision_id"]: row for row in cur.fetchall()}


def _render_manifest(rows):
    if not rows:
        return "<p class='empty'>Sin manifiesto registrado.</p>"
    items = []
    for r in rows:
        challenger = (
            f"{_badge('CHALLENGER', _ARTIFACT_STATUS_COLOR['CHALLENGER'])} {r['challenger_id']} (desde {_fmt_dt(r['challenger_desde'])})"
            if r["challenger_id"] else "<span class='empty'>sin challenger en evaluacion</span>"
        )
        items.append(f"""
        <div class="card">
          <div class="card-title">Ambiente: <code>{r['ambiente']}</code></div>
          <div class="row"><b>{_badge('CHAMPION', _ARTIFACT_STATUS_COLOR['CHAMPION'])}</b> {r['champion_id']}
            <span class="muted">desde {_fmt_dt(r['champion_desde'])}{f" ({r['champion_por']})" if r['champion_por'] else ""}</span></div>
          <div class="row">{challenger}</div>
        </div>
        """)
    return "".join(items)


def _render_artifacts(rows):
    if not rows:
        return "<p class='empty'>Sin artefactos registrados.</p>"
    trs = []
    for r in rows:
        color = _ARTIFACT_STATUS_COLOR.get(r["status"], "#57606a")
        metricas = r["metricas"] or {}
        metricas_str = ", ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in list(metricas.items())[:4])
        trs.append(f"""
        <tr>
          <td><code>{r['artifact_id']}</code></td>
          <td>{r['tipo']}</td>
          <td>{_badge(r['status'], color)}</td>
          <td class="muted small">{r['descripcion'] or '-'}</td>
          <td class="muted small">{metricas_str or '-'}</td>
          <td class="muted small">{_fmt_dt(r['promoted_at'])}</td>
        </tr>
        """)
    return f"""
    <table>
      <thead><tr><th>artifact_id</th><th>tipo</th><th>status</th><th>descripcion</th><th>metricas</th><th>promoted_at</th></tr></thead>
      <tbody>{''.join(trs)}</tbody>
    </table>
    """


def _render_candidates(cands):
    if not cands:
        return "<span class='empty'>sin candidatas evaluadas</span>"
    rows = []
    for c in cands[:MAX_CANDIDATES_PER_DECISION]:
        estilo = "font-weight:700;" if c["fue_elegido"] else ""
        marca = " ⭐" if c["fue_elegido"] else ""
        rows.append(
            f"<div style='{estilo}'>#{c['rank_posicion']} route_id={c['route_id']}{marca} "
            f"<span class='muted small'>puntaje={_fmt_num(c['puntaje'], 3)} profit=${_fmt_num(c['profit_estimado'], 0)}</span></div>"
        )
    extra = len(cands) - MAX_CANDIDATES_PER_DECISION
    if extra > 0:
        rows.append(f"<div class='muted small'>+ {extra} candidatas mas</div>")
    return "".join(rows)


def _render_result(res):
    if not res:
        return "<span class='empty'>pendiente (Reconciler no construido)</span>"
    return (
        f"profit real=${_fmt_num(res['profit_apl_real'], 0)} "
        f"rpm={_fmt_num(res['rpm_efectivo'], 2)} "
        f"deadhead={_fmt_num(res['pct_deadhead'], 1)}% "
        f"<span class='muted small'>({_fmt_dt(res['timestamp_resultado'])})</span>"
    )


def _render_decisions(decisions, candidates_by_decision, results_by_decision):
    if not decisions:
        return "<p class='empty'>Sin decisiones registradas todavia.</p>"
    trs = []
    for d in decisions:
        color = _DECISION_STATUS_COLOR.get(d["status"], "#57606a")
        cands = candidates_by_decision.get(d["decision_id"], [])
        res = results_by_decision.get(d["decision_id"])
        trs.append(f"""
        <tr>
          <td><code>{d['decision_id']}</code><div class="muted small">{_fmt_dt(d['timestamp_decision'])}</div></td>
          <td>{_badge(d['status'], color)}</td>
          <td>{d['truck_id'] or '-'}<div class="muted small">{d['tipo_equipo'] or '-'}</div></td>
          <td>{d['zone_actual_code'] or '-'} &rarr; {d['destino_final_code'] or '-'}</td>
          <td class="small">{_render_candidates(cands)}</td>
          <td class="small">{_render_result(res)}</td>
        </tr>
        """)
    return f"""
    <table>
      <thead><tr><th>decision_id</th><th>status</th><th>truck</th><th>origen &rarr; destino</th><th>candidatas (&#11088; elegida)</th><th>resultado real</th></tr></thead>
      <tbody>{''.join(trs)}</tbody>
    </table>
    """


_PAGE_TEMPLATE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Praxis -- Knowledge State</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; background: #f6f8fa; color: #1f2328; margin: 0; padding: 24px 32px 60px; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  h2 {{ font-size: 15px; text-transform: uppercase; letter-spacing: .04em; color: #57606a; margin: 32px 0 10px; border-bottom: 1px solid #d0d7de; padding-bottom: 6px; }}
  .subtitle {{ color: #57606a; font-size: 13px; margin-bottom: 8px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d0d7de; border-radius: 6px; overflow: hidden; }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #eaeef2; vertical-align: top; font-size: 13px; }}
  th {{ background: #f6f8fa; font-weight: 600; color: #57606a; }}
  tr:last-child td {{ border-bottom: none; }}
  code {{ background: #eaeef2; border-radius: 4px; padding: 1px 5px; font-size: 12px; }}
  .muted {{ color: #57606a; }}
  .small {{ font-size: 12px; }}
  .empty {{ color: #8c959f; font-style: italic; }}
  .card {{ background: #fff; border: 1px solid #d0d7de; border-radius: 6px; padding: 12px 16px; margin-bottom: 8px; }}
  .card-title {{ font-weight: 600; margin-bottom: 6px; }}
  .row {{ margin: 4px 0; font-size: 13px; }}
  .refresh {{ font-size: 12px; color: #8c959f; }}
</style>
</head>
<body>
  <h1>Praxis -- Knowledge State</h1>
  <div class="subtitle">Panel de solo lectura, generado en vivo desde Postgres. <span class="refresh">Recarga la pagina para ver el estado mas reciente.</span></div>

  <h2>Capa 4 -- Gobernanza y Manifiesto</h2>
  {manifest}

  <h2>Capa 2 -- Artefactos</h2>
  {artifacts}

  <h2>Capa 1 -- Decision Ledger (ultimas {max_decisions})</h2>
  {decisions}
</body>
</html>
"""


@router.get("/admin", response_class=HTMLResponse)
def admin_page():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            manifest_rows = _fetch_manifest(cur)
            artifact_rows = _fetch_artifacts(cur)
            decision_rows = _fetch_decisions(cur)
            decision_ids = [d["decision_id"] for d in decision_rows]
            candidates_by_decision = _fetch_candidates(cur, decision_ids)
            results_by_decision = _fetch_results(cur, decision_ids)
    finally:
        conn.close()

    html = _PAGE_TEMPLATE.format(
        manifest=_render_manifest(manifest_rows),
        artifacts=_render_artifacts(artifact_rows),
        decisions=_render_decisions(decision_rows, candidates_by_decision, results_by_decision),
        max_decisions=MAX_DECISIONS,
    )
    return HTMLResponse(content=html)
