import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.models.database import get_conn
from backend.routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_LAYOUT_PATH = Path(__file__).parent.parent.parent / "config" / "line_layout.json"


def _load_layout() -> dict:
    return json.loads(_LAYOUT_PATH.read_text(encoding="utf-8"))


@router.get("/line-layout")
def get_line_layout(_user=Depends(get_current_user)):
    if not _LAYOUT_PATH.exists():
        raise HTTPException(404, "라인 레이아웃 설정 파일 없음")
    return _load_layout()


@router.get("/equipment-status")
def get_equipment_status(
    days: int = Query(30, ge=7, le=180),
    _user=Depends(get_current_user),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM equipment WHERE is_active = 1")
            equip_list = cur.fetchall()

            cur.execute(
                """
                SELECT
                    dr.suspected_equipment_id AS equipment_id,
                    COUNT(*)                  AS claim_count,
                    GROUP_CONCAT(DISTINCT dr.defect_type) AS defect_types
                FROM defect_reports dr
                WHERE dr.suspected_equipment_id IS NOT NULL
                  AND dr.production_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                GROUP BY dr.suspected_equipment_id
                """,
                (days,),
            )
            claim_map = {r["equipment_id"]: r for r in cur.fetchall()}

            cur.execute(
                """
                SELECT
                    lph.equipment_id,
                    COUNT(*)                                        AS total_lots,
                    SUM(CASE WHEN lph.result = 'NG' THEN 1 ELSE 0 END) AS ng_count
                FROM lot_process_history lph
                    JOIN production_lots pl ON pl.lot_no = lph.lot_no
                WHERE pl.production_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                GROUP BY lph.equipment_id
                """,
                (days,),
            )
            ng_map = {r["equipment_id"]: r for r in cur.fetchall()}

    result = []
    for eq in equip_list:
        eid = eq["equipment_id"]
        claims = claim_map.get(eid, {})
        ng_info = ng_map.get(eid, {})
        claim_count = claims.get("claim_count", 0)
        ng_count = ng_info.get("ng_count", 0)
        total_lots = ng_info.get("total_lots", 0)
        ng_rate = round(ng_count / total_lots, 4) if total_lots > 0 else 0.0

        if claim_count >= 5 or ng_rate >= 0.10:
            status = "critical"
        elif claim_count >= 2 or ng_rate >= 0.05:
            status = "warning"
        else:
            status = "normal"

        result.append({
            "equipment_id": eid,
            "name": eq["name"],
            "process_id": eq["process_id"],
            "process_name": eq["process_name"],
            "status": status,
            "claim_count": claim_count,
            "defect_types": claims.get("defect_types", ""),
            "ng_rate": ng_rate,
            "total_lots": total_lots,
            "ng_count": ng_count,
        })

    return {"period_days": days, "equipment": result}


@router.get("/equipment/{equipment_id}")
def get_equipment_detail(
    equipment_id: str,
    _user=Depends(get_current_user),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM equipment WHERE equipment_id = %s", (equipment_id,)
            )
            equip = cur.fetchone()
            if not equip:
                raise HTTPException(404, "설비를 찾을 수 없음")

            cur.execute(
                """
                SELECT dr.report_id, dr.document_no, dr.defect_type,
                       dr.lot_no, dr.production_date, dr.report_status,
                       dr.root_cause_analysis, dr.corrective_action
                FROM defect_reports dr
                WHERE dr.suspected_equipment_id = %s
                ORDER BY dr.production_date DESC
                LIMIT 20
                """,
                (equipment_id,),
            )
            claims = cur.fetchall()

            cur.execute(
                """
                SELECT lph.lot_no, lph.process_id, lph.result,
                       lph.started_at, lph.finished_at,
                       pl.production_date, pl.shift
                FROM lot_process_history lph
                    JOIN production_lots pl ON pl.lot_no = lph.lot_no
                WHERE lph.equipment_id = %s
                ORDER BY lph.started_at DESC
                LIMIT 50
                """,
                (equipment_id,),
            )
            history = cur.fetchall()

    return {
        "equipment": equip,
        "recent_claims": claims,
        "process_history": history,
    }


@router.get("/lot/{lot_no}")
def get_lot_detail(
    lot_no: str,
    _user=Depends(get_current_user),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM production_lots WHERE lot_no = %s", (lot_no,)
            )
            lot = cur.fetchone()
            if not lot:
                raise HTTPException(404, "LOT를 찾을 수 없음")

            cur.execute(
                """
                SELECT lph.*, e.name AS equipment_name
                FROM lot_process_history lph
                    JOIN equipment e ON e.equipment_id = lph.equipment_id
                WHERE lph.lot_no = %s
                ORDER BY lph.process_order
                """,
                (lot_no,),
            )
            process_history = cur.fetchall()

            cur.execute(
                """
                SELECT report_id, document_no, defect_type,
                       report_status, suspected_equipment_id
                FROM defect_reports
                WHERE lot_no = %s
                ORDER BY report_id DESC
                """,
                (lot_no,),
            )
            linked_claims = cur.fetchall()

    return {
        "lot": lot,
        "process_history": process_history,
        "linked_claims": linked_claims,
    }
