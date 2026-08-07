# Third-Party Licenses & API Terms — Weatherly AI

This document lists all third-party tools, models, APIs, libraries, and datasets used by Weatherly AI, along with their licenses, terms of use, and any compliance requirements. This should be reviewed before deployment or project submission.

## AI / LLM Layer

| Component | License / Terms | Notes & Obligations |
|----------|-----------------|---------------------|
| **Ollama** (runtime) | MIT | Fully open source with no additional restrictions. |
| **Llama 3** (via Ollama) | [Meta Llama 3 Community License](https://www.llama.com/llama3/license/) | Requires inclusion of the Meta Llama 3 license and the **"Built with Meta Llama 3"** attribution if the application is distributed. Outputs may not be used to train competing foundation models. A separate commercial license is required only if the application exceeds 700 million monthly active users. |
| **Mistral 7B** (via Ollama) | Apache 2.0 | Fully permissive open-source license with no attribution requirements beyond the Apache 2.0 license. Recommended for simpler licensing compliance. |

---

## Weather & Geographic Data

| Component | License / Terms | Notes & Obligations |
|----------|-----------------|---------------------|
| **NASA POWER API** | Public Domain (U.S. Government) | Free to use. NASA recommends attribution but does not require it. Applications should respect published rate limits. |
| **Open-Meteo API** | CC BY 4.0 (data), MIT (source code) | Weather data requires attribution: **"Weather data by Open-Meteo.com."** Commercial use must comply with Open-Meteo's API terms. |
| **OpenStreetMap / Nominatim** | OpenStreetMap data: ODbL<br>Nominatim: Usage Policy | Requests should be limited to one per second, use a valid identifying User-Agent, display **© OpenStreetMap contributors**, and avoid bulk or automated scraping. |
| **Leaflet + OpenStreetMap Tiles** | Leaflet: BSD-2-Clause<br>OpenStreetMap Tile Usage Policy | Free to use with attribution. Suitable for development and moderate traffic. High-volume deployments should consider a commercial tile provider or self-hosted tiles. |

---

## Backend & Machine Learning Libraries

| Component | License |
|----------|----------|
| FastAPI | MIT |
| Pydantic | MIT |
| Uvicorn | BSD-3-Clause |
| Prophet | MIT |
| scikit-learn | BSD-3-Clause |
| pandas | BSD-3-Clause |
| NumPy | BSD-3-Clause |
| joblib | BSD-3-Clause |
| requests | Apache 2.0 |

All backend libraries use permissive open-source licenses and require no additional compliance beyond retaining their respective licenses.

---

## Frontend Libraries

| Component | License |
|----------|----------|
| React / React DOM | MIT |
| Vite | MIT |
| Tailwind CSS | MIT |
| Radix UI | MIT |
| lucide-react | ISC |
| framer-motion | MIT |
| Leaflet | BSD-2-Clause |
| react-leaflet | Hippocratic License 2.1 |
| html2canvas | MIT |
| html-to-image | MIT |

**Note:** `react-leaflet` is licensed under the **Hippocratic License 2.1**, which is an ethical-source license rather than an OSI-approved open-source license. It is suitable for normal software development but includes restrictions on use by organizations involved in specific human rights violations.

---

## Compliance Checklist

Before submitting or deploying Weatherly AI, ensure that:

1. A valid contact email is included in the **Nominatim User-Agent** header.
2. **© OpenStreetMap contributors** attribution remains visible wherever OpenStreetMap data or tiles are displayed.
3. If using **Llama 3**, include the required Meta Llama 3 license and attribution notice.
4. Environment files (`.env`) remain excluded from version control.
5. All third-party licenses are included in the project's documentation where required.

---

## Overall License Summary

Weatherly AI primarily relies on permissively licensed open-source software, including MIT, BSD, Apache 2.0, ISC, and public-domain resources. The only components with additional licensing considerations are:

- **Llama 3**, which is distributed under the Meta Llama 3 Community License.
- **react-leaflet**, which uses the Hippocratic License 2.1.
- **OpenStreetMap/Open-Meteo**, which require proper attribution when their data is displayed or used.

No paid APIs or proprietary services are required for the current implementation.