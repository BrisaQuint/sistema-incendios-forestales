# Technical currency review — FireWatch Architecture Spine

**Reviewed:** 2026-10-07  
**Scope:** Decisions in `ARCHITECTURE-SPINE.md` that name current libraries, frameworks, versions, or rely on existing/starter project settings. The spine and application were not changed.

## Verdict

The explicit version targets in the Stack table are published and current against the official registries/releases checked on the review date. Node.js `24.21.0` is an LTS release; Vite `8.3.3` declares support for Node `^20.19.0 || >=22.12.0`, so the proposed Node target satisfies its engine range.

No clearly obsolete or unavailable pinned version was found. The main gate items are stack completeness/reproducibility (Pydantic is named but has no version entry, and the application stack is not yet in the project manifests) and confirming that the existing Python floor is a deliberate support decision rather than inherited scaffolding.

## Findings

### F-01 — Pydantic is a committed contract dependency but absent from the baseline [Medium]

**Location:** Spine AD-9 and Stack table (around lines 100, 157–173).

AD-9 makes “FastAPI/Pydantic contracts” authoritative, but the Stack table versions FastAPI without listing Pydantic. It is an important part of request/response validation and OpenAPI schema generation; leaving it implicit makes the architecture baseline incomplete. This is not a present runtime failure: FastAPI brings a compatible Pydantic dependency. It is a reproducibility/contract-version gap when implementation dependencies are locked.

**Current reality:** The application `pyproject.toml` and `uv.lock` currently contain neither FastAPI nor Pydantic. Official FastAPI documentation describes its Pydantic-based data validation/schema behavior; Pydantic publishes its own versioned model/schema contract.

**Recommendation:** Add Pydantic to the baseline with a version compatible with the chosen FastAPI release, or explicitly state that it is transitive and that the implementation lockfile is authoritative. Add an OpenAPI/schema regression check so upgrades cannot silently change API contracts.

**Evidence:**
- FastAPI tutorial: <https://fastapi.tiangolo.com/tutorial/>
- Pydantic documentation: <https://docs.pydantic.dev/latest/>
- Current project manifest: `sistema-incendios-forestales/pyproject.toml`

### F-02 — The Python floor is real project configuration, but its status as a deliberate decision is unproven [Low]

**Location:** Stack table, Python row (around line 163).

The claim that Python `>=3.13` is an “existing project requirement” is accurate: it appears in `pyproject.toml` and `uv.lock`, and `.python-version` selects `3.13`. However, the project manifest still contains the scaffold placeholder “Add your description here,” so the Python setting may be inherited starter configuration rather than a consciously selected deployment/support floor. The lock currently resolves the scientific data stack under that constraint.

**Current reality:** `pyproject.toml` declares `requires-python = ">=3.13"` and dependencies `cffdrs`, `geopandas>=1.1.4`, and `pandas>=3.0.6`. The existing lock resolves GeoPandas `1.1.4`, pandas `3.0.6`, and cffdrs `0.3.0` from Git commit `7d8931e64fca7c5a0d0f34a14d258215a3b9506d`. The lock and `.python-version` corroborate the configured floor, not whether it was chosen for production/runtime compatibility.

**Recommendation:** Keep the current floor if intentional, but record why Python 3.13 is the minimum supported interpreter and verify the selected `cffdrs`/GIS stack on the actual target platforms. Otherwise revise the requirement and regenerate the lock when implementation starts. Mark this as an inherited project constraint until that decision is made.

**Evidence:**
- `sistema-incendios-forestales/pyproject.toml`, `.python-version`, and `uv.lock`
- GeoPandas release metadata: <https://pypi.org/project/geopandas/1.1.4/>
- pandas release metadata: <https://pypi.org/project/pandas/3.0.6/>
- cffdrs locked source: <https://github.com/cffdrs/cffdrs_py/tree/7d8931e64fca7c5a0d0f34a14d258215a3b9506d>

### F-03 — The proposed web/application versions are not yet an installable, locked stack [Medium]

**Location:** Stack table and its note, “Lock exact dependencies when implementation begins” (around lines 157–173).

The listed FastAPI, Uvicorn, OpenAI SDK, React, React DOM, TypeScript, Vite, and Node targets are sensible current candidates, but they are not the repository’s current application dependencies. The existing Python manifest/lock cover only the scientific data pipeline; there is not yet a frontend package manifest or frontend lockfile. Consequently, the table demonstrates version currency, not a reproducible resolution or tested cross-stack compatibility.

**Current reality:** Official package registries contain each exact target named by the spine: FastAPI `0.142.4`, Uvicorn `0.54.0`, OpenAI Python SDK `3.26.0`, React and React DOM `19.3.0`, TypeScript `7.0.2`, and Vite `8.3.3`. The official Node release page lists `24.21.0` as LTS (and Node 26 as Current) on the review date. Vite’s package metadata accepts Node `^20.19.0 || >=22.12.0`, which includes Node 24.21.0.

**Recommendation:** Keep the distinction between candidate baseline and installed reality explicit. When implementation begins, add the backend dependencies to `pyproject.toml`, create and commit a frontend manifest/lockfile and Node pin, resolve the complete dependency graph, and run install/build/API-schema checks on the chosen Python and Node versions. Recheck the baselines then rather than treating the 2026-10-07 registry snapshot as permanent.

**Evidence (official package/release sources):**
- FastAPI `0.142.4`: <https://pypi.org/project/fastapi/0.142.4/>
- Uvicorn `0.54.0`: <https://pypi.org/project/uvicorn/0.54.0/>
- OpenAI Python SDK `3.26.0`: <https://pypi.org/project/openai/3.26.0/>
- React `19.3.0`: <https://www.npmjs.com/package/react/v/19.3.0>
- React DOM `19.3.0`: <https://www.npmjs.com/package/react-dom/v/19.3.0>
- TypeScript `7.0.2`: <https://www.npmjs.com/package/typescript/v/7.0.2>
- Vite `8.3.3`, including Node engine range: <https://registry.npmjs.org/vite/8.3.3>
- Node.js release status: <https://nodejs.org/en/about/previous-releases>
- Node.js `24.21.0` release artifacts: <https://nodejs.org/dist/v24.21.0/>

## Version/current-reality checklist

| Spine decision | Review result |
| --- | --- |
| Python `>=3.13` | Matches manifest, lock, and `.python-version`; confirm intentional support floor (F-02). |
| FastAPI `0.142.4`; Uvicorn `0.54.0`; OpenAI Python SDK `3.26.0` | Exact releases are published on PyPI; absent from current project manifest/lock pending implementation (F-03). |
| React / React DOM `19.3.0`; TypeScript `7.0.2`; Vite `8.3.3` | Exact releases are published on npm; Vite’s engine range includes the proposed Node 24 runtime (F-03). |
| Node.js `24.21.0` LTS | Official Node release page reports v24.21.0 as LTS on the review date; compatible with Vite’s declared engine range. |
| Data stack: pandas, GeoPandas, cffdrs | Present in the current uv lock at pandas `3.0.6`, GeoPandas `1.1.4`, cffdrs `0.3.0` (locked Git commit); consistent with declared constraints. |
| Pydantic | Named in the architecture’s API contract but not versioned in the Stack table or current project dependencies (F-01). |
| SQLite / GeoJSON | Treated as a standard-library database interface and interchange format; no external framework version is committed in the spine. |

