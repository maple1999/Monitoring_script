from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import os


def _string_contains_any(s: str, terms: List[str]) -> bool:
    ls = s.lower()
    return any(t.lower() in ls for t in terms)


def collect_kaggle_contests(
    search_terms: List[str],
    include_kw: List[str],
    exclude_kw: List[str],
    limit: int,
    pages: int = 1,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi  # type: ignore
    except Exception:
        return [], "kaggle_pkg_missing"

    try:
        api = KaggleApi()
        api.authenticate()
    except Exception as e:
        return [], f"kaggle_auth_failed: {e}"

    results: List[Dict[str, Any]] = []
    seen_refs = set()

    # Normalize terms
    search_terms = search_terms or [""]

    try:
        for term in search_terms:
            for page in range(1, max(1, pages) + 1):
                comps = api.competitions_list(search=term, page=page)  # type: ignore[attr-defined]
                if not comps:
                    break
                for c in comps:
                    try:
                        ref = getattr(c, "ref", None) or getattr(c, "id", None)
                        if not ref or ref in seen_refs:
                            continue
                        seen_refs.add(ref)
                        title = getattr(c, "title", None) or str(ref)
                        # some fields may not exist; getattr with default
                        deadline = getattr(c, "deadline", None)
                        if isinstance(deadline, (int, float)):
                            deadline = None
                        description = getattr(c, "description", None) or getattr(c, "subTitle", None) or ""
                        org = getattr(c, "organizationName", None) or getattr(c, "organization_name", None)
                        reward = getattr(c, "reward", None)
                        eval_metric = getattr(c, "evaluationMetric", None)
                        max_team = getattr(c, "maxTeamSize", None)
                        max_daily = getattr(c, "maxDailySubmissions", None)
                        category = getattr(c, "category", None)
                        host_segment = getattr(c, "hostSegment", None)
                        url = f"https://www.kaggle.com/competitions/{ref}"

                        # keyword filter on title + description
                        blob = f"{title}\n{description}"
                        if include_kw and not _string_contains_any(blob, include_kw):
                            continue
                        if exclude_kw and _string_contains_any(blob, exclude_kw):
                            continue

                        # Try enrich with competition_view
                        try:
                            if hasattr(api, "competition_view"):
                                det = api.competition_view(ref)  # type: ignore[attr-defined]
                                # Often same fields; keep getattr fallback
                                reward = reward or getattr(det, "reward", None)
                                eval_metric = eval_metric or getattr(det, "evaluationMetric", None)
                                max_team = max_team or getattr(det, "maxTeamSize", None)
                                max_daily = max_daily or getattr(det, "maxDailySubmissions", None)
                                org = org or getattr(det, "organizationName", None)
                                category = category or getattr(det, "category", None)
                                host_segment = host_segment or getattr(det, "hostSegment", None)
                        except Exception:
                            pass

                        req_parts: List[str] = []
                        if eval_metric:
                            req_parts.append(f"评测指标: {eval_metric}")
                        if max_daily:
                            req_parts.append(f"每日提交上限: {max_daily}")
                        if max_team:
                            req_parts.append(f"团队规模上限: {max_team}")
                        requirements = "; ".join(req_parts) if req_parts else None

                        tags = ["cv"]
                        for t in (category, host_segment):
                            if t:
                                tags.append(str(t).lower())

                        results.append(
                            {
                                "source": "kaggle",
                                "url": url,
                                "title": title,
                                "summary": description or None,
                                "requirements": requirements,
                                "deadline": str(deadline) if deadline else None,
                                "company_or_org": org,
                                "tags": tags,
                            }
                        )
                        if len(results) >= limit:
                            return results, None
                # continue to next page
    except Exception as e:
        return results, f"kaggle_api_error: {e}"

    return results, None
