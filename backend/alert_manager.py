import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models import Watchlist, Alert, Camera


# OCR Character Substitution Map for common visual confusions
OCR_CONFUSIONS = {
    '0': 'O', 'O': '0', 'Q': '0',
    '1': 'I', 'I': '1', 'L': '1',
    '2': 'Z', 'Z': '2',
    '5': 'S', 'S': '5',
    '8': 'B', 'B': '8',
}


def normalize_plate(plate: str) -> str:
    """Removes spaces, hyphens, and converts to uppercase alphanumeric."""
    if not plate:
        return ""
    return re.sub(r'[^A-Za-z0-9]', '', plate).upper()


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculates Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def is_ocr_equivalent_or_similar(detected: str, target: str, max_distance: int = 1) -> tuple[bool, str, float]:
    """
    Checks if detected plate is exact match, OCR-confused equivalent, or within edit distance.
    Returns: (is_match, match_type, similarity_score)
    """
    if detected == target:
        return True, "exact", 1.0

    # Length check: if length differs by more than max_distance, cannot match
    if abs(len(detected) - len(target)) > max_distance:
        return False, "none", 0.0

    # Calculate standard Levenshtein distance
    dist = levenshtein_distance(detected, target)
    max_len = max(len(detected), len(target))
    similarity = 1.0 - (dist / max_len) if max_len > 0 else 0.0

    if dist == 0:
        return True, "exact", 1.0
    elif dist <= max_distance:
        # Check if difference is purely OCR character ambiguity
        if len(detected) == len(target):
            diffs = [(d, t) for d, t in zip(detected, target) if d != t]
            if all(OCR_CONFUSIONS.get(d) == t or OCR_CONFUSIONS.get(t) == d for d, t in diffs):
                return True, "fuzzy_ocr", similarity

        return True, "fuzzy", similarity

    return False, "none", similarity


class AlertManager:
    @staticmethod
    async def process_detection(
        session: AsyncSession,
        detected_plate: str,
        camera_id: str,
        crop_path: Optional[str] = None,
        detection_timestamp: Optional[datetime] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates detected plate against the active Watchlist.
        If matched, inserts an Alert into database and returns alert payload.
        """
        clean_detected = normalize_plate(detected_plate)
        if not clean_detected:
            return None

        # Fetch all watchlist entries
        result = await session.execute(select(Watchlist))
        watchlist_items = result.scalars().all()

        best_match: Optional[Watchlist] = None
        best_match_type = "none"
        highest_score = 0.0

        for item in watchlist_items:
            clean_target = normalize_plate(item.plate_number)
            is_match, match_type, score = is_ocr_equivalent_or_similar(clean_detected, clean_target)

            if is_match and score > highest_score:
                highest_score = score
                best_match = item
                best_match_type = match_type
                if match_type == "exact":
                    break

        if best_match:
            ts = detection_timestamp or datetime.now(timezone.utc)
            alert = Alert(
                plate_number=clean_detected,
                camera_id=camera_id,
                timestamp=ts,
                reason=f"[{best_match_type.upper()} MATCH: {best_match.plate_number}] {best_match.reason}",
                severity=best_match.severity,
                match_type=best_match_type,
                matched_watchlist_plate=best_match.plate_number,
                crop_path=crop_path,
                acknowledged=False
            )
            session.add(alert)
            await session.commit()
            await session.refresh(alert)

            # Fetch camera info for enriched payload
            cam_res = await session.execute(select(Camera).where(Camera.id == camera_id))
            cam = cam_res.scalar_one_or_none()

            return {
                "alert_id": alert.id,
                "plate_number": clean_detected,
                "matched_watchlist_plate": best_match.plate_number,
                "match_type": best_match_type,
                "similarity": round(highest_score, 3),
                "reason": alert.reason,
                "severity": alert.severity,
                "camera_id": camera_id,
                "camera_name": cam.name if cam else camera_id,
                "camera_latitude": cam.latitude if cam else None,
                "camera_longitude": cam.longitude if cam else None,
                "camera_zone": cam.zone if cam else "Central",
                "timestamp": ts.isoformat(),
                "crop_path": crop_path
            }

        return None
