"""Package registry collectors: PyPI, npm, crates.io. Best-effort discovery."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import PackageData, Result

# Hard-coded known mappings; collectors gracefully return failure for everything else.
KNOWN_PACKAGES: dict[str, list[dict[str, str]]] = {
    "BAML": [
        {"registry": "pypi", "package": "baml-py"},
        {"registry": "npm", "package": "@boundaryml/baml"},
    ],
    "Atuin": [
        {"registry": "crates", "package": "atuin"},
    ],
    "Mem0": [
        {"registry": "pypi", "package": "mem0ai"},
        {"registry": "npm", "package": "mem0ai"},
    ],
    "Rasa": [
        {"registry": "pypi", "package": "rasa"},
    ],
    "Tigris Data": [
        {"registry": "npm", "package": "@tigrisdata/core"},
    ],
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    r = await client.get(url, timeout=20.0, follow_redirects=True)
    return r


async def _pypi(client: httpx.AsyncClient, pkg: str) -> Result[PackageData]:
    try:
        # pypistats for downloads
        stats = await _get(client, f"https://pypistats.org/api/packages/{pkg}/recent")
        downloads_30d: Optional[int] = None
        if stats.status_code == 200:
            d = stats.json().get("data") or {}
            downloads_30d = d.get("last_month")

        # PyPI JSON for version count
        meta = await _get(client, f"https://pypi.org/pypi/{pkg}/json")
        version_count = None
        latest = None
        if meta.status_code == 200:
            j = meta.json()
            version_count = len(j.get("releases") or {})
            latest = j.get("info", {}).get("version")
        elif meta.status_code == 404:
            return Result(success=False, error=f"pypi {pkg} not found", source="pypi")

        downloads_90d = downloads_30d * 3 if downloads_30d is not None else None
        return Result(
            success=True,
            data=PackageData(
                registry="pypi",
                package=pkg,
                downloads_30d=downloads_30d,
                downloads_90d=downloads_90d,
                version_count=version_count,
                latest_version=latest,
            ),
            source="pypi",
        )
    except Exception as e:
        return Result(success=False, error=str(e), source="pypi")


async def _npm(client: httpx.AsyncClient, pkg: str) -> Result[PackageData]:
    try:
        today = datetime.utcnow().date()
        start_30 = today - timedelta(days=30)
        start_90 = today - timedelta(days=90)

        r30 = await _get(
            client,
            f"https://api.npmjs.org/downloads/range/{start_30.isoformat()}:{today.isoformat()}/{pkg}",
        )
        r90 = await _get(
            client,
            f"https://api.npmjs.org/downloads/range/{start_90.isoformat()}:{today.isoformat()}/{pkg}",
        )

        downloads_30d = None
        downloads_90d = None
        if r30.status_code == 200:
            j = r30.json()
            downloads = j.get("downloads") or []
            downloads_30d = sum(d.get("downloads", 0) for d in downloads)
        if r90.status_code == 200:
            j = r90.json()
            downloads = j.get("downloads") or []
            downloads_90d = sum(d.get("downloads", 0) for d in downloads)

        meta = await _get(client, f"https://registry.npmjs.org/{pkg}")
        version_count = None
        latest = None
        if meta.status_code == 200:
            j = meta.json()
            version_count = len(j.get("versions") or {})
            latest = (j.get("dist-tags") or {}).get("latest")
        elif meta.status_code == 404:
            return Result(success=False, error=f"npm {pkg} not found", source="npm")

        return Result(
            success=True,
            data=PackageData(
                registry="npm",
                package=pkg,
                downloads_30d=downloads_30d,
                downloads_90d=downloads_90d,
                version_count=version_count,
                latest_version=latest,
            ),
            source="npm",
        )
    except Exception as e:
        return Result(success=False, error=str(e), source="npm")


async def _crates(client: httpx.AsyncClient, pkg: str) -> Result[PackageData]:
    try:
        r = await _get(client, f"https://crates.io/api/v1/crates/{pkg}")
        if r.status_code == 404:
            return Result(success=False, error=f"crate {pkg} not found", source="crates")
        if r.status_code != 200:
            return Result(success=False, error=f"crates returned {r.status_code}", source="crates")
        j = r.json()
        crate = j.get("crate") or {}
        versions = j.get("versions") or []

        # crates.io exposes recent_downloads (last 90 days)
        downloads_90d = crate.get("recent_downloads")
        # Approximate 30d as 1/3 of 90d (crates.io doesn't expose 30d directly)
        downloads_30d = int(downloads_90d / 3) if downloads_90d else None

        latest = (versions[0].get("num") if versions else None) or crate.get("max_version")
        return Result(
            success=True,
            data=PackageData(
                registry="crates",
                package=pkg,
                downloads_30d=downloads_30d,
                downloads_90d=downloads_90d,
                version_count=len(versions) or None,
                latest_version=latest,
            ),
            source="crates",
        )
    except Exception as e:
        return Result(success=False, error=str(e), source="crates")


async def collect_packages(company_name: str) -> list[Result[PackageData]]:
    entries = KNOWN_PACKAGES.get(company_name, [])
    if not entries:
        return [Result(success=False, error="no known package mappings", source="packages")]

    results: list[Result[PackageData]] = []
    async with httpx.AsyncClient() as client:
        for entry in entries:
            reg = entry["registry"]
            pkg = entry["package"]
            if reg == "pypi":
                results.append(await _pypi(client, pkg))
            elif reg == "npm":
                results.append(await _npm(client, pkg))
            elif reg == "crates":
                results.append(await _crates(client, pkg))
    return results
